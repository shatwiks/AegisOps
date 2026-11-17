import { useEffect, useState } from 'react';
import type { ReplayFrame, ReplayListItem, ReplayTimeline } from '../types';

interface Props {
  replays: ReplayListItem[];
  activeReplay: ReplayTimeline | null;
  frameIndex: number;
  onSelectReplay: (replayId: string) => void;
  onChangeFrame: (idx: number) => void;
  onExitReplay: () => void;
}

export function ReplayController({
  replays,
  activeReplay,
  frameIndex,
  onSelectReplay,
  onChangeFrame,
  onExitReplay,
}: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);

  const totalFrames = activeReplay?.frames.length ?? 0;
  const currentFrame: ReplayFrame | undefined = activeReplay?.frames[frameIndex];

  useEffect(() => {
    if (!playing || !activeReplay) return;
    if (frameIndex >= activeReplay.frames.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      onChangeFrame(Math.min(activeReplay.frames.length - 1, frameIndex + 1));
    }, Math.round(1800 / speed));
    return () => window.clearTimeout(timer);
  }, [playing, speed, frameIndex, activeReplay, onChangeFrame]);

  if (!activeReplay) return null;

  return (
    <section className="replay-banner" aria-label="Recorded Incident Replay Controller">
      <div className="section-head" style={{ marginBottom: '0.6rem' }}>
        <div>
          <span className="badge badge-warn" style={{ marginRight: 8 }}>
            RECORDED REPLAY — No live cluster changes
          </span>
          <span className="muted-pill" style={{ marginRight: 8 }}>{activeReplay.source_badge}</span>
          <strong>{activeReplay.title}</strong>
        </div>
        <button type="button" className="btn btn-primary" onClick={onExitReplay}>
          Exit Replay -&gt; Return to Live View
        </button>
      </div>

      <div className="inline-form" style={{ marginTop: 0, alignItems: 'center' }}>
        <select
          aria-label="Choose recorded replay"
          value={activeReplay.replay_id}
          onChange={(e) => {
            setPlaying(false);
            onSelectReplay(e.target.value);
          }}
        >
          {replays.map((r) => (
            <option key={r.replay_id} value={r.replay_id}>
              [{r.source_badge}] {r.title} ({r.final_state})
            </option>
          ))}
        </select>

        <button
          type="button"
          className="btn btn-secondary"
          disabled={frameIndex <= 0}
          onClick={() => {
            setPlaying(false);
            onChangeFrame(Math.max(0, frameIndex - 1));
          }}
        >
          ◀ Step Back
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={frameIndex >= totalFrames - 1}
          onClick={() => {
            setPlaying(false);
            onChangeFrame(Math.min(totalFrames - 1, frameIndex + 1));
          }}
        >
          Step Forward ▶
        </button>

        <select
          aria-label="Replay speed"
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value) as 1 | 2 | 4)}
        >
          <option value={1}>1x</option>
          <option value={2}>2x</option>
          <option value={4}>4x</option>
        </select>

        <input
          type="range"
          aria-label="Seek timeline frame"
          min={0}
          max={Math.max(0, totalFrames - 1)}
          value={frameIndex}
          onChange={(e) => {
            setPlaying(false);
            onChangeFrame(Number(e.target.value));
          }}
          style={{ flex: 1, minWidth: 140 }}
        />
        <span className="mono-small">
          Frame {frameIndex + 1}/{totalFrames} (+{currentFrame?.elapsed_seconds ?? 0}s)
        </span>
      </div>

      {currentFrame && (
        <div className="replay-frame-box">
          <div className="row-top">
            <span>
              <strong>Step {currentFrame.lifecycle_step}/7 ({currentFrame.state}):</strong> {currentFrame.headline}
            </span>
            <span className="mono-small">{new Date(currentFrame.timestamp).toLocaleString()}</span>
          </div>
          <p className="muted" style={{ fontSize: '0.84rem', margin: '0.25rem 0' }}>{currentFrame.narration}</p>
          <div className="diff-grid" style={{ marginTop: 6 }}>
            <div className="mono-small">
              Historical K8s snapshot: <code>{JSON.stringify(currentFrame.topology_overlay.historical_k8s_snapshot)}</code>
            </div>
            <div className="mono-small">
              Watchdog snapshot: <code>{JSON.stringify(currentFrame.watchdog_progress)}</code>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
