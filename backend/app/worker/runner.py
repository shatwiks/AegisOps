"""Durable transactional outbox worker loop with lease recovery and full lifecycle execution."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.cmdb.graph import get_blast_radius
from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory
from app.domain.state_machine import IncidentState, transition_incident
from app.k8s.executor import KubernetesExecutor, execute_remediation_attempt
from app.models.entities import (
    ApprovalRequest,
    Asset,
    AuditRecord,
    DemoRun,
    Incident,
    IncidentEvent,
    OutboxJob,
    SystemControlFlag,
)
from app.observability.langfuse_tracer import record_sanitized_llm_trace
from app.policy.engine import evaluate_remediation_policy
from app.rag.diagnosis import DiagnosisInvocationError, generate_diagnosis_with_record
from app.rag.retriever import hybrid_search_runbooks
from app.redis_client import build_redis_client
from app.worker.locks import RedisTargetLease
from app.worker.watchdog import HealthProbeSample, verify_sustained_recovery

logger = logging.getLogger("aegisops.worker")


class _AutomationPausedHold(RuntimeError):
    """Internal signal that automation is paused by an operator; requeue without penalty."""


async def _is_automation_paused(session: AsyncSession) -> bool:
    flag = (
        await session.execute(
            select(SystemControlFlag).where(SystemControlFlag.key == "automation_paused")
        )
    ).scalar_one_or_none()
    return bool(flag and flag.bool_value)


async def _sync_demo_run_status(
    session: AsyncSession,
    *,
    incident: Incident,
    new_status: str,
    completed: bool = False,
) -> None:
    if not incident.demo_run_id:
        return
    run = (
        await session.execute(select(DemoRun).where(DemoRun.id == incident.demo_run_id))
    ).scalar_one_or_none()
    if run is None:
        return
    run.status = new_status
    if run.incident_id is None:
        run.incident_id = incident.id
    if completed and run.completed_at is None:
        run.completed_at = datetime.now(UTC)


async def claim_next_outbox_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int = 120,
    incident_id: uuid.UUID | None = None,
) -> OutboxJob | None:
    """Atomically claim one pending job or recover an expired claimed job via SKIP LOCKED."""
    now = datetime.now(UTC)
    stmt = select(OutboxJob).where(
        or_(
            and_(OutboxJob.status == "PENDING", OutboxJob.available_at <= now),
            and_(
                OutboxJob.status == "CLAIMED",
                OutboxJob.lease_expires_at.is_not(None),
                OutboxJob.lease_expires_at < now,
            ),
        )
    )
    if incident_id is not None:
        stmt = stmt.where(OutboxJob.incident_id == incident_id)
    stmt = stmt.order_by(OutboxJob.created_at.asc()).with_for_update(skip_locked=True).limit(1)
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None

    job.status = "CLAIMED"
    job.worker_id = worker_id
    job.claimed_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    await session.flush()
    return job


async def _handle_triage_job(
    job: OutboxJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    executor: KubernetesExecutor,
) -> None:
    if job.incident_id is None:
        return
    incident_id = job.incident_id
    async with session_factory() as session, session.begin():
        incident = (
            await session.execute(select(Incident).where(Incident.id == incident_id))
        ).scalar_one()

        if incident.state == IncidentState.OPEN.value:
            await transition_incident(
                session,
                incident_id=incident.id,
                to_state=IncidentState.TRIAGING,
                actor="system:outbox-worker",
                actor_role="worker",
                event_type="TRIAGE_STARTED",
                policy_decision="TRIAGING",
            )

        asset = (
            (
                await session.execute(select(Asset).where(Asset.id == incident.primary_asset_id))
            ).scalar_one_or_none()
            if incident.primary_asset_id
            else None
        )
        downstream_slugs: list[str] = []
        if asset is not None:
            blast = await get_blast_radius(session, asset.slug)
            downstream_slugs = [d.slug for d in blast.downstream_impacts]

        docs = await hybrid_search_runbooks(
            session,
            f"{incident.alertname} {asset.slug if asset else ''} {incident.summary_sanitized}",
            settings,
            top_k=5,
        )

    proposal = None
    prompt_record: dict[str, Any] = {
        "captured": False,
        "reason": "Diagnosis invocation failed or timed out",
    }
    try:
        proposal, prompt_record = await generate_diagnosis_with_record(
            alertname=incident.alertname,
            asset_slug=asset.slug if asset else (incident.unknown_asset_identifier or "unknown"),
            severity=incident.severity,
            summary_sanitized=incident.summary_sanitized,
            blast_downstream_slugs=downstream_slugs,
            docs=docs,
            settings=settings,
            redis_client=redis_client,
        )
    except DiagnosisInvocationError as exc:
        prompt_record = {"captured": False, "reason": str(exc)[:240]}
        logger.warning("Diagnosis failed safely for incident %s: %s", incident.id, exc)

    decision = evaluate_remediation_policy(
        asset=asset,
        alertname=incident.alertname,
        summary_sanitized=incident.summary_sanitized,
        retrieved_docs=docs,
        proposal=proposal,
        settings=settings,
    )

    record_sanitized_llm_trace(
        settings=settings,
        trace_name="incident_triage",
        incident_id=str(incident.id),
        input_payload={"alertname": incident.alertname, "summary": incident.summary_sanitized},
        output_payload={
            "proposal": proposal.model_dump() if proposal else None,
            "decision": decision.decision,
            "playbook_id": decision.playbook_id,
        },
        metadata={"severity": incident.severity},
    )

    async with session_factory() as session, session.begin():
        now = datetime.now(UTC)
        diag_blob: dict[str, Any] = {
            "proposal": proposal.model_dump() if proposal else None,
            "citations": [
                {
                    "slug": d.slug,
                    "title": d.title,
                    "doc_type": d.doc_type,
                    "vector_similarity": round(d.vector_similarity, 4),
                    "lexical_score": round(d.lexical_score, 4),
                    "rrf_score": round(d.rrf_score, 6),
                }
                for d in docs
            ],
            "policy_checks": decision.checks,
        }

        target_state = IncidentState(decision.target_state)
        paused_now = await _is_automation_paused(session)
        updated_inc = await transition_incident(
            session,
            incident_id=incident_id,
            to_state=target_state,
            actor="system:policy-engine",
            actor_role="policy",
            event_type="POLICY_EVALUATED",
            policy_decision=decision.decision,
            details_sanitized={
                "decision": decision.decision,
                "playbook_id": decision.playbook_id,
                "risk_tier": decision.risk_tier,
                "reason": decision.reason,
                "automation_paused": paused_now,
            },
            timestamp_field="triaged_at",
            extra_updates={
                "diagnosis_json": diag_blob,
                "sanitized_prompt_json": prompt_record,
                "proposed_playbook_id": decision.playbook_id,
                "proposed_parameters_json": decision.sanitized_parameters,
                "confidence_score": docs[0].vector_similarity if docs else None,
                "refusal_reason": decision.reason
                if target_state == IncidentState.ESCALATED
                else None,
            },
        )
        if target_state == IncidentState.AWAITING_APPROVAL:
            await _sync_demo_run_status(session, incident=updated_inc, new_status="AWAITING_APPROVAL")
        elif target_state == IncidentState.ESCALATED:
            await _sync_demo_run_status(
                session, incident=updated_inc, new_status="ESCALATED", completed=True
            )
        else:
            await _sync_demo_run_status(session, incident=updated_inc, new_status="ACTIVE")

        if target_state == IncidentState.READY_TO_REMEDIATE:
            session.add(
                OutboxJob(
                    incident_id=job.incident_id,
                    job_type="EXECUTE_REMEDIATION",
                    dedup_job_key=f"EXECUTE_REMEDIATION:{job.incident_id}:{decision.playbook_id}",
                    payload_sanitized_json={
                        "incident_id": str(job.incident_id),
                        "playbook_id": decision.playbook_id,
                        "parameters": decision.sanitized_parameters,
                    },
                    status="PENDING",
                    available_at=now,
                )
            )
        elif target_state == IncidentState.AWAITING_APPROVAL and asset is not None:
            import hashlib
            import json as _json

            dep_name = asset.k8s_deployment_name or asset.name
            target_uid = f"unfetched-{asset.slug}"
            target_rv = "0"
            try:
                snap = await executor.read_deployment_snapshot(
                    cluster=asset.cluster,
                    namespace=asset.namespace,
                    deployment_name=dep_name,
                )
                target_uid = snap.uid
                target_rv = snap.resource_version
            except Exception as exc:
                logger.warning("Could not snapshot target K8s deployment %s: %s", dep_name, exc)

            params_hash = hashlib.sha256(
                _json.dumps(decision.sanitized_parameters, sort_keys=True).encode("utf-8")
            ).hexdigest()
            session.add(
                ApprovalRequest(
                    incident_id=job.incident_id,
                    playbook_id=decision.playbook_id or "",
                    playbook_version=decision.playbook_version or "1.0.0",
                    parameters_hash=params_hash,
                    parameters_json=decision.sanitized_parameters,
                    target_asset_slug=asset.slug,
                    target_k8s_uid=target_uid,
                    target_resource_version=target_rv,
                    status="PENDING",
                    requested_at=now,
                    expires_at=now + timedelta(minutes=15),
                )
            )


async def _handle_execute_job(
    job: OutboxJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    executor: KubernetesExecutor,
) -> None:
    if job.incident_id is None:
        return
    incident_id = job.incident_id
    paused_hold = False
    async with session_factory() as session, session.begin():
        inc = (
            await session.execute(
                select(Incident).where(Incident.id == incident_id).with_for_update()
            )
        ).scalar_one()
        if inc.state != IncidentState.READY_TO_REMEDIATE.value:
            logger.info(
                "Skipping EXECUTE_REMEDIATION for incident %s in state %s", inc.id, inc.state
            )
            return

        if await _is_automation_paused(session):
            existing_hold = (
                await session.execute(
                    select(IncidentEvent.id).where(
                        IncidentEvent.incident_id == inc.id,
                        IncidentEvent.event_type == "AUTOMATION_PAUSED_HOLD",
                    )
                )
            ).first()
            if existing_hold is None:
                session.add(
                    IncidentEvent(
                        incident_id=inc.id,
                        event_type="AUTOMATION_PAUSED_HOLD",
                        from_state=inc.state,
                        to_state=inc.state,
                        actor="system:control-flag",
                        details_sanitized_json={
                            "note": "Execution held because automation_paused flag is enabled by an operator."
                        },
                        created_at=datetime.now(UTC),
                    )
                )
            paused_hold = True
        else:
            asset = (
                await session.execute(select(Asset).where(Asset.id == inc.primary_asset_id))
            ).scalar_one()
            approval: ApprovalRequest | None = None
            if job.payload_sanitized_json.get("approval_id"):
                approval = (
                    await session.execute(
                        select(ApprovalRequest).where(
                            ApprovalRequest.id == uuid.UUID(job.payload_sanitized_json["approval_id"])
                        )
                    )
                ).scalar_one_or_none()

            await transition_incident(
                session,
                incident_id=inc.id,
                to_state=IncidentState.REMEDIATING,
                actor="system:outbox-worker",
                actor_role="worker",
                event_type="REMEDIATION_STARTED",
                policy_decision="REMEDIATING",
                details_sanitized={"playbook_id": inc.proposed_playbook_id},
            )

    if paused_hold:
        raise _AutomationPausedHold("Automation paused by operator")

    lease = RedisTargetLease(
        redis_client,
        f"{asset.cluster}:{asset.namespace}:{asset.k8s_deployment_name or asset.name}",
        ttl_ms=settings.aegisops_lock_ttl_ms,
        owner_prefix=job.worker_id or "worker",
    )
    acquired = await lease.acquire()
    if not acquired:
        # Lock contention is NOT resolution or success; record audit and retry later
        async with session_factory() as session, session.begin():
            session.add(
                AuditRecord(
                    incident_id=job.incident_id,
                    actor_sub=job.worker_id or "worker",
                    actor_role="worker",
                    action_type="LOCK_CONTENTION_SKIP",
                    policy_decision="SKIPPED_LOCK_CONTENTION",
                    details_json={"resource": lease.resource_key},
                )
            )
        raise RuntimeError(f"Lock contention on {lease.resource_key}; retrying")

    try:
        attempt = await execute_remediation_attempt(
            session_factory,
            incident_id=job.incident_id,
            asset=asset,
            playbook_id=inc.proposed_playbook_id or "",
            raw_parameters=inc.proposed_parameters_json or {},
            idempotency_key=f"exec:{job.incident_id}:{inc.proposed_playbook_id}:{job.attempts}",
            lease=lease,
            executor=executor,
            approval=approval,
            actor_sub=approval.decided_by_sub
            if approval and approval.decided_by_sub
            else "system:outbox-worker",
            actor_role=approval.decided_by_role
            if approval and approval.decided_by_role
            else "worker",
        )
    finally:
        await lease.release()

    async with session_factory() as session, session.begin():
        now = datetime.now(UTC)
        verifying_inc = await transition_incident(
            session,
            incident_id=incident_id,
            to_state=IncidentState.VERIFYING,
            actor="system:outbox-worker",
            actor_role="worker",
            event_type="RECOVERY_VERIFICATION_STARTED",
            policy_decision="VERIFYING",
            timestamp_field="mutated_at",
            extra_updates={
                "verification_state_json": {
                    "status": "observing",
                    "started_at": now.isoformat(),
                    "first_recovered_at": None,
                    "elapsed_healthy_seconds": 0.0,
                    "window_seconds": float(settings.aegisops_recovery_window_seconds),
                    "sample_count": 0,
                    "reset_count": 0,
                    "last_reset_reason": None,
                    "samples": [],
                }
            },
            details_sanitized={"execution_id": str(attempt.id), "status": attempt.status},
        )
        await _sync_demo_run_status(session, incident=verifying_inc, new_status="VERIFYING")
        session.add(
            OutboxJob(
                incident_id=job.incident_id,
                job_type="VERIFY_RECOVERY",
                dedup_job_key=f"VERIFY_RECOVERY:{job.incident_id}:{attempt.id}",
                payload_sanitized_json={"incident_id": str(job.incident_id)},
                status="PENDING",
                available_at=now,
            )
        )


async def _handle_verify_job(
    job: OutboxJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    executor: KubernetesExecutor,
) -> None:
    if job.incident_id is None:
        return
    incident_id = job.incident_id
    async with session_factory() as session:
        inc = (
            await session.execute(select(Incident).where(Incident.id == incident_id))
        ).scalar_one()
        if inc.state != IncidentState.VERIFYING.value:
            return
        asset = (
            await session.execute(select(Asset).where(Asset.id == inc.primary_asset_id))
        ).scalar_one()

    recent_samples: list[dict[str, Any]] = []

    async def _on_watchdog_sample(
        *,
        sample: HealthProbeSample,
        started_at: datetime,
        first_recovered_at: datetime | None,
        elapsed_healthy_seconds: float,
        window_seconds: float,
        sample_count: int,
        reset_count: int,
        last_reset_reason: str | None,
    ) -> None:
        recent_samples.append(
            {
                "checked_at": sample.checked_at.isoformat(),
                "healthy": sample.healthy,
                "rollout_ready": sample.rollout_ready,
                "http_probe_ok": sample.http_probe_ok,
                "metrics_fresh_and_ok": sample.metrics_fresh_and_ok,
                "reasons": list(sample.reasons),
                "metrics_snapshot": sample.metrics_snapshot,
            }
        )
        if len(recent_samples) > 20:
            del recent_samples[0 : len(recent_samples) - 20]

        async with session_factory() as tick_session, tick_session.begin():
            row = (
                await tick_session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            row.verification_state_json = {
                "status": "observing",
                "started_at": started_at.isoformat(),
                "first_recovered_at": first_recovered_at.isoformat() if first_recovered_at else None,
                "elapsed_healthy_seconds": round(elapsed_healthy_seconds, 1),
                "window_seconds": float(window_seconds),
                "sample_count": sample_count,
                "reset_count": reset_count,
                "last_reset_reason": last_reset_reason,
                "last_sample": recent_samples[-1],
                "samples": list(recent_samples),
            }
            if row.first_recovered_at is None and first_recovered_at is not None:
                row.first_recovered_at = first_recovered_at

    ok, first_rec_at, samples = await verify_sustained_recovery(
        asset=asset,
        settings=settings,
        executor=executor,
        on_sample_callback=_on_watchdog_sample,
    )

    async with session_factory() as session, session.begin():
        cur_inc = (
            await session.execute(select(Incident).where(Incident.id == incident_id))
        ).scalar_one()
        final_verif = dict(cur_inc.verification_state_json or {})
        if ok:
            final_verif["status"] = "passed"
            resolved_inc = await transition_incident(
                session,
                incident_id=incident_id,
                to_state=IncidentState.RESOLVED,
                actor="system:watchdog",
                actor_role="watchdog",
                event_type="SUSTAINED_RECOVERY_CONFIRMED",
                policy_decision="RESOLVED",
                timestamp_field="resolved_at",
                extra_updates={
                    "first_recovered_at": first_rec_at,
                    "verification_state_json": final_verif,
                },
                details_sanitized={
                    "sample_count": len(samples),
                    "recovery_window_seconds": settings.aegisops_recovery_window_seconds,
                    "last_metrics": samples[-1].metrics_snapshot if samples else {},
                },
            )
            await _sync_demo_run_status(
                session, incident=resolved_inc, new_status="COMPLETED", completed=True
            )
        else:
            last_reasons = samples[-1].reasons if samples else ["No samples collected"]
            final_verif["status"] = "failed"
            escalated_inc = await transition_incident(
                session,
                incident_id=incident_id,
                to_state=IncidentState.ESCALATED,
                actor="system:watchdog",
                actor_role="watchdog",
                event_type="RECOVERY_VERIFICATION_FAILED",
                policy_decision="ESCALATED",
                details_sanitized={"sample_count": len(samples), "reasons": last_reasons},
                extra_updates={
                    "refusal_reason": "; ".join(last_reasons),
                    "verification_state_json": final_verif,
                },
            )
            await _sync_demo_run_status(
                session, incident=escalated_inc, new_status="ESCALATED", completed=True
            )


async def _dispatch_claimed_job(
    job: OutboxJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    executor: KubernetesExecutor,
) -> None:
    job_id = job.id
    try:
        if job.job_type == "TRIAGE_INCIDENT":
            await _handle_triage_job(
                job,
                session_factory=session_factory,
                redis_client=redis_client,
                settings=settings,
                executor=executor,
            )
        elif job.job_type == "EXECUTE_REMEDIATION":
            await _handle_execute_job(
                job,
                session_factory=session_factory,
                redis_client=redis_client,
                settings=settings,
                executor=executor,
            )
        elif job.job_type == "VERIFY_RECOVERY":
            await _handle_verify_job(
                job,
                session_factory=session_factory,
                settings=settings,
                executor=executor,
            )
        elif job.job_type == "RUN_DEMO_SCENARIO":
            from app.showcase.scenarios import execute_demo_scenario_job

            await execute_demo_scenario_job(
                job,
                session_factory=session_factory,
                settings=settings,
                executor=executor,
            )
        elif job.job_type == "INDEX_RUNBOOK":
            from app.api.runbooks import process_runbook_indexing_job

            await process_runbook_indexing_job(
                job,
                session_factory=session_factory,
                settings=settings,
            )

        async with session_factory() as session, session.begin():
            row = (
                await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))
            ).scalar_one()
            row.status = "COMPLETED"
            row.completed_at = datetime.now(UTC)
            row.lease_expires_at = None
    except _AutomationPausedHold as exc:
        logger.info("Outbox job %s paused by automation_paused flag: %s", job_id, exc)
        async with session_factory() as session, session.begin():
            row = (
                await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))
            ).scalar_one()
            row.status = "PENDING"
            row.lease_expires_at = None
            row.attempts = max(0, row.attempts - 1)
            row.available_at = datetime.now(UTC) + timedelta(seconds=5)
    except Exception as exc:
        logger.exception("Outbox job %s (%s) failed: %s", job.id, job.job_type, exc)
        async with session_factory() as session, session.begin():
            row = (
                await session.execute(select(OutboxJob).where(OutboxJob.id == job_id))
            ).scalar_one()
            row.last_error_sanitized = f"{type(exc).__name__}: {str(exc)[:300]}"
            row.lease_expires_at = None
            if row.attempts >= row.max_attempts:
                row.status = "DEAD_LETTER"
            else:
                row.status = "PENDING"
                row.available_at = datetime.now(UTC) + timedelta(seconds=min(5 * row.attempts, 30))


async def run_worker_once(
    *,
    worker_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    executor: KubernetesExecutor,
) -> bool:
    """Process at most one outbox job cleanly. Returns True if a job was processed."""
    await redis_client.setex(
        f"aegisops:worker:heartbeat:{worker_id}", 30, datetime.now(UTC).isoformat()
    )

    async with session_factory() as session, session.begin():
        job = await claim_next_outbox_job(session, worker_id=worker_id)
        if job is None:
            return False

    await _dispatch_claimed_job(
        job,
        session_factory=session_factory,
        redis_client=redis_client,
        settings=settings,
        executor=executor,
    )
    return True


async def run_worker_loop() -> None:
    settings = get_settings()
    engine: AsyncEngine = build_engine(settings)
    factory = build_session_factory(engine)
    redis_client = build_redis_client(settings)
    executor = KubernetesExecutor(settings)
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    stop_event = asyncio.Event()
    concurrency = asyncio.Semaphore(4)
    in_flight: set[asyncio.Task[None]] = set()

    def _request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    logger.info("AegisOps outbox worker started (worker_id=%s, concurrency=4)", worker_id)
    try:
        while not stop_event.is_set():
            await redis_client.setex(
                f"aegisops:worker:heartbeat:{worker_id}", 30, datetime.now(UTC).isoformat()
            )
            async with concurrency:
                async with factory() as session, session.begin():
                    job = await claim_next_outbox_job(session, worker_id=worker_id)

            if job is not None:

                def _spawn_job(claimed_job: OutboxJob) -> None:
                    async def _bounded_run() -> None:
                        async with concurrency:
                            await _dispatch_claimed_job(
                                claimed_job,
                                session_factory=factory,
                                redis_client=redis_client,
                                settings=settings,
                                executor=executor,
                            )

                    task = asyncio.create_task(_bounded_run())
                    in_flight.add(task)
                    task.add_done_callback(in_flight.discard)

                _spawn_job(job)
                continue

            await asyncio.sleep(1.5)
    finally:
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
        await redis_client.aclose()
        await engine.dispose()
        logger.info("AegisOps outbox worker exited cleanly")


if __name__ == "__main__":
    asyncio.run(run_worker_loop())
