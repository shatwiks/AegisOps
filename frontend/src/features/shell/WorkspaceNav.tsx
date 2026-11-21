import { Activity, BookOpen, Eye, FileCheck2, PlayCircle, Terminal } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import type { MainNav } from '../../hooks/useUrlConsoleState';

interface Props {
  mainNav: MainNav;
  technicalMode: boolean;
  replaysCount: number;
  replayActive: boolean;
  onChangeNav: (nav: MainNav) => void;
  onToggleTechnicalMode: () => void;
  onStartReplay: () => void;
}

/** Underline workspace navigation bar plus presentation-mode and replay triggers. */
export function WorkspaceNav({
  mainNav,
  technicalMode,
  replaysCount,
  replayActive,
  onChangeNav,
  onToggleTechnicalMode,
  onStartReplay,
}: Props) {
  return (
    <nav className="workspace-nav" aria-label="Console navigation and presentation controls">
      <div className="workspace-nav__inner">
        <div className="workspace-tabs" role="group" aria-label="Workspace tabs">
          <button
            type="button"
            aria-pressed={mainNav === 'console'}
            className={`ws-tab ${mainNav === 'console' ? 'active' : ''}`}
            onClick={() => onChangeNav('console')}
          >
            <Activity size={15} aria-hidden="true" />
            Operations Console
          </button>
          <button
            type="button"
            aria-pressed={mainNav === 'knowledge'}
            className={`ws-tab ${mainNav === 'knowledge' ? 'active' : ''}`}
            onClick={() => onChangeNav('knowledge')}
          >
            <BookOpen size={15} aria-hidden="true" />
            Knowledge Base &amp; Privacy Playground
          </button>
          <button
            type="button"
            aria-pressed={mainNav === 'evidence'}
            className={`ws-tab ${mainNav === 'evidence' ? 'active' : ''}`}
            onClick={() => onChangeNav('evidence')}
          >
            <FileCheck2 size={15} aria-hidden="true" />
            Engineering Evidence
          </button>
        </div>

        <div className="workspace-actions">
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={technicalMode}
            onClick={onToggleTechnicalMode}
          >
            {technicalMode ? <Terminal size={14} aria-hidden="true" /> : <Eye size={14} aria-hidden="true" />}
            View: {technicalMode ? 'Technical Deep-Dive' : 'Executive Overview'}
          </Button>
          {replaysCount > 0 && !replayActive && (
            <Button variant="secondary" size="sm" onClick={onStartReplay}>
              <PlayCircle size={14} aria-hidden="true" />
              Recorded Replay ({replaysCount})
            </Button>
          )}
        </div>
      </div>
    </nav>
  );
}
