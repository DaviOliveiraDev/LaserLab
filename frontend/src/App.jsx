import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import JobQueue from './components/JobQueue';
import LensPreview from './components/LensPreview';
import CalibrationPanel from './components/CalibrationPanel';
import LogsView from './components/LogsView';
import TemplateManager from './components/TemplateManager';
import TemplateEditor from './components/TemplateEditor';

// New simulation components
import OMAViewer from './components/OMAViewer';
import GcodePreview from './components/GcodePreview';
import SimulatorPanel from './components/SimulatorPanel';

const BACKEND_URL = 'http://localhost:8000';


export default function App() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  
  // Derive selected job from jobs array to avoid stale closures
  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null;

  const [calibration, setCalibration] = useState(null);
  const [logs, setLogs] = useState([]);
  const [backendError, setBackendError] = useState(false);
  const [status, setStatus] = useState({
    monitoring: false,
    laser_connected: false,
    laser_port: 'COM_MOCK',
    job_queue_count: 0
  });

  // Machine Simulator Status
  const [machineStatus, setMachineStatus] = useState({
    status: 'READY',
    temperature: 22.5,
    laser_power_w: 0.0,
    safety_door_locked: true,
    door_open_alarm: false,
    overtemp_alarm: false,
    power_drop_alarm: false,
    current_job_id: null,
    current_gcode_line: null,
    current_gcode_index: 0,
    total_gcode_lines: 0,
    progress_pct: 0.0
  });

  // Selected job G-code text
  const [gcodeText, setGcodeText] = useState('');

  // Tab State / Sidebar navigation: 'production' | 'simulation' | 'machine' | 'logs' | 'templates'
  const [activeTab, setActiveTab] = useState('production');
  
  // Template Editor State: 'list', 'create', 'edit'
  const [templateEditorState, setTemplateEditorState] = useState('list');
  const [editingTemplate, setEditingTemplate] = useState(null);

  // Fetch job Gcode on selection
  useEffect(() => {
    if (!selectedJobId) {
      setGcodeText('');
      return;
    }
    let active = true;
    fetch(`${BACKEND_URL}/api/jobs/${selectedJobId}/gcode`)
      .then((res) => {
        if (res.ok) return res.text();
        return '';
      })
      .then((text) => {
        if (active) {
          setGcodeText(text);
        }
      })
      .catch((err) => console.error(err));
    return () => {
      active = false;
    };
  }, [selectedJobId]);

  // Pull all state updates from local FastAPI web server
  const fetchData = useCallback(() => {
    // 1. Fetch Status
    fetch(`${BACKEND_URL}/api/system/status`)
      .then((res) => {
        if (!res.ok) throw new Error('Backend error');
        return res.json();
      })
      .then((data) => {
        setStatus(data);
        setBackendError(false);
        setCalibration((prev) => prev || data.calibration);
      })
      .catch((err) => {
        console.error('Error fetching system status:', err);
        setBackendError(true);
        setStatus({
          monitoring: false,
          laser_connected: false,
          laser_port: 'OFFLINE',
          job_queue_count: 0
        });
      });

    // 2. Fetch Jobs List
    fetch(`${BACKEND_URL}/api/jobs`)
      .then((res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((data) => {
        setJobs(data);
        setBackendError(false);
      })
      .catch((err) => {
        console.error('Error fetching jobs queue:', err);
      });

    // 3. Fetch System Logs
    fetch(`${BACKEND_URL}/api/logs`)
      .then((res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((data) => {
        setLogs(data);
        setBackendError(false);
      })
      .catch((err) => {
        console.error('Error fetching logs:', err);
      });

    // 4. Fetch Virtual Laser Machine status
    fetch(`${BACKEND_URL}/api/simulator/machine`)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error();
      })
      .then((data) => {
        setMachineStatus(data);
      })
      .catch((err) => {
        console.error('Error fetching machine status:', err);
      });
  }, []);

  useEffect(() => {
    // Load initial data
    fetchData();

    // High frequency telemetry updates (every 800ms)
    const timer = setInterval(fetchData, 800);
    return () => clearInterval(timer);
  }, [fetchData]);

  // Handler to stream laser G-code commands to virtual/physical hardware
  const handleStartLaser = () => {
    if (!selectedJobId) return;
    fetch(`${BACKEND_URL}/api/jobs/${selectedJobId}/stream`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) return res.json().then(d => { throw new Error(d.detail || 'Não foi possível iniciar a gravação') });
        fetchData();
      })
      .catch((err) => alert(err.message));
  };

  // Handler to cancel active laser sequence
  const handleAbortLaser = () => {
    if (!selectedJobId) return;
    fetch(`${BACKEND_URL}/api/jobs/${selectedJobId}/stop`, { method: 'POST' })
      .then((res) => {
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Handler to trigger geometric reprocessing on modified offsets
  const handleReprocessJob = () => {
    if (!selectedJobId) return;
    fetch(`${BACKEND_URL}/api/jobs/${selectedJobId}/reprocess`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setJobs((prevJobs) => prevJobs.map((j) => (j.id === data.id ? data : j)));
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Handler to save calibration adjustments
  const handleSaveCalibration = (calData) => {
    return fetch(`${BACKEND_URL}/api/calibration`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(calData),
    })
      .then((res) => res.json())
      .then((data) => {
        setCalibration(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Handler to inject a programmatically generated mock OMA file
  const handleCreateMockJob = () => {
    fetch(`${BACKEND_URL}/api/system/mock-job`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setJobs((prevJobs) => [data.job, ...prevJobs]);
        setSelectedJobId(data.job.id);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Alarm Toggling Handler
  const handleTriggerAlarm = (alarmName, value) => {
    fetch(`${BACKEND_URL}/api/simulator/machine/alarm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alarm_name: alarmName, value }),
    })
      .then((res) => res.json())
      .then((data) => {
        setMachineStatus(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Alarm Resets
  const handleResetAlarms = () => {
    fetch(`${BACKEND_URL}/api/simulator/machine/reset`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setMachineStatus(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const isStreaming = selectedJob?.status.startsWith('Streaming') || machineStatus?.status === 'PROCESSING';
  const isReady = selectedJob?.status === 'Ready' || selectedJob?.status === 'Success';
  const isMachineError = machineStatus?.status === 'ERROR';

  return (
    <div className="app-layout-wrapper">
      {/* SCADA Sidebar Compact */}
      <aside className="scada-sidebar">
        <div className="sidebar-logo">
          ⚡ LASER SCADA v1.0
        </div>
        <button 
          className={`sidebar-btn ${activeTab === 'production' ? 'active' : ''}`}
          onClick={() => setActiveTab('production')}
        >
          🕹️ Produção
        </button>
        <button 
          className={`sidebar-btn ${activeTab === 'simulation' ? 'active' : ''}`}
          onClick={() => setActiveTab('simulation')}
        >
          ⚙️ Simulação
        </button>
        <button 
          className={`sidebar-btn ${activeTab === 'machine' ? 'active' : ''}`}
          onClick={() => setActiveTab('machine')}
        >
          🔧 Máquina
        </button>
        <button 
          className={`sidebar-btn ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('templates');
            setTemplateEditorState('list');
          }}
        >
          🗃️ Templates
        </button>
        <button 
          className={`sidebar-btn ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => setActiveTab('logs')}
        >
          📑 Histórico Logs
        </button>
      </aside>

      {/* Main Workspace Frame */}
      <div className="main-content-area">
        
        {/* Header telemetry panel */}
        <header className="dashboard-header glass-panel">
          <div className="header-title-section">
            <h1>LaserLab Virtual-Industrial</h1>
            <p>Módulo de Simulação Operacional e Validação G-code em Lentes Freeform</p>
          </div>

          <div className="system-status-indicator">
            {/* Watcher Directory Status */}
            <div className={`status-badge ${status.monitoring ? 'online' : 'offline'}`}>
              <span className="dot pulse" />
              OMA Watcher: {status.monitoring ? 'Ativo' : 'Inativo'}
            </div>

            {/* Virtual Laser hardware port status */}
            <div className={`status-badge ${machineStatus.status === 'ERROR' ? 'offline' : 'online'}`}>
              <span className="dot pulse" />
              CLP Status: {machineStatus.status}
            </div>

            <div className={`status-badge ${status.laser_connected ? 'online' : 'offline'}`}>
              <span className="dot pulse" />
              Virtual Port ({status.laser_port}): {status.laser_connected ? 'CONECTADO' : 'OFFLINE'}
            </div>
          </div>
        </header>

        {backendError && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            color: '#fca5a5',
            padding: '10px 16px',
            borderRadius: '10px',
            fontSize: '0.8rem',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            <span>⚠️</span>
            <div>
              <strong>ERRO DE CONEXÃO COM O SERVIDOR:</strong> O backend FastAPI (porta 8000) não está respondendo.
            </div>
          </div>
        )}

        {/* Dynamic Panel rendering */}
        {activeTab === 'production' && (
          <div className="dashboard-grid-scada">
            {/* Left Column: Queue & raw OMA parser */}
            <div className="panel-column-dense scada-queue-panel">
              <JobQueue 
                jobs={jobs} 
                selectedJob={selectedJob} 
                onSelectJob={(job) => setSelectedJobId(job ? job.id : null)} 
                onCreateMockJob={handleCreateMockJob}
              />
              <OMAViewer job={selectedJob} />
            </div>

            {/* Center Column: Lens Preview CAD & execution triggers */}
            <div className="panel-column glass-panel" style={{ height: '100%' }}>
              <div className="panel-header">
                <span>Visualização CAD e Geometria da Lente</span>
                {selectedJob && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {selectedJob.filename} ({selectedJob.status})
                  </span>
                )}
              </div>
              
              <div className="panel-body" style={{ padding: 0 }}>
                <LensPreview 
                  selectedJob={selectedJob} 
                  backendUrl={BACKEND_URL} 
                  machineStatus={machineStatus}
                />
              </div>

              {/* Action Trigger Panels */}
              {selectedJob && (
                <div className="laser-control-actions">
                  <button 
                    className="btn btn-glass"
                    onClick={handleReprocessJob}
                    disabled={isStreaming}
                  >
                    Re-calcular Geometria
                  </button>

                  {isStreaming ? (
                    <button 
                      className="btn btn-red"
                      onClick={handleAbortLaser}
                    >
                      🛑 Abortar Gravação
                    </button>
                  ) : (
                    <button 
                      className="btn btn-cyan"
                      onClick={handleStartLaser}
                      disabled={(!isReady && selectedJob.status !== 'Failed') || isMachineError}
                    >
                      ⚡ Executar Gravação Laser
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Active Gcode console & scrolling system logs */}
            <div className="panel-column-dense">
              <GcodePreview 
                gcodeText={gcodeText} 
                currentLineIndex={machineStatus.current_gcode_index}
                isStreaming={isStreaming}
              />
              <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', flex: 1, maxHeight: '250px' }}>
                <div className="panel-header" style={{ padding: '8px 12px', fontSize: '0.8rem' }}>
                  <span>LOGS OPERACIONAIS EM TEMPO REAL</span>
                </div>
                <div className="panel-body" style={{ padding: '8px', overflow: 'hidden' }}>
                  <LogsView logs={logs} />
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'simulation' && (
          <div className="dashboard-grid-scada">
            {/* Left Column: Queue */}
            <div className="panel-column-dense scada-queue-panel">
              <JobQueue 
                jobs={jobs} 
                selectedJob={selectedJob} 
                onSelectJob={(job) => setSelectedJobId(job ? job.id : null)} 
                onCreateMockJob={handleCreateMockJob}
              />
            </div>

            {/* Center Column: Lens Preview CAD & execution triggers */}
            <div className="panel-column glass-panel" style={{ height: '100%' }}>
              <div className="panel-header">
                <span>Visualização CAD e Geometria da Lente</span>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <LensPreview 
                  selectedJob={selectedJob} 
                  backendUrl={BACKEND_URL} 
                  machineStatus={machineStatus}
                />
              </div>
              {selectedJob && (
                <div className="laser-control-actions">
                  {isStreaming ? (
                    <button className="btn btn-red" onClick={handleAbortLaser}>🛑 Abortar Gravação</button>
                  ) : (
                    <button 
                      className="btn btn-cyan" 
                      onClick={handleStartLaser} 
                      disabled={(!isReady && selectedJob.status !== 'Failed') || isMachineError}
                    >
                      ⚡ Executar Gravação Laser
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Right Column: Simulator Fault Injection Panel */}
            <SimulatorPanel 
              machineStatus={machineStatus}
              onTriggerAlarm={handleTriggerAlarm}
              onResetAlarms={handleResetAlarms}
              onCreateMockJob={handleCreateMockJob}
              backendUrl={BACKEND_URL}
            />
          </div>
        )}

        {activeTab === 'machine' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: '16px', flex: 1, minHeight: 0 }}>
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="panel-header">🔧 Calibração Métrica do Campo Galvo</div>
              <div className="panel-body">
                <CalibrationPanel 
                  calibration={calibration} 
                  onSaveCalibration={handleSaveCalibration} 
                />
              </div>
            </div>
            <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <h3>Especificações do Laser Virtual</h3>
              <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Tipo de Laser:</p>
                <p><strong>Mock Galvo UV Laser (355 nm)</strong></p>
              </div>
              <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Área Escaneável:</p>
                <p><strong>110 mm x 110 mm</strong></p>
              </div>
              <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Velocidade Máxima:</p>
                <p><strong>4000 mm/s</strong></p>
              </div>
              <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '6px' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Comunicação serial:</p>
                <p>COM_MOCK (Simulador Emulado em Tempo Real)</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'templates' && (
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }} className="glass-panel">
            {templateEditorState === 'list' ? (
              <TemplateManager 
                backendUrl={BACKEND_URL}
                onEditTemplate={(tpl) => {
                  setEditingTemplate(tpl);
                  setTemplateEditorState('edit');
                }}
                onCreateTemplate={() => {
                  setEditingTemplate(null);
                  setTemplateEditorState('create');
                }}
              />
            ) : (
              <TemplateEditor 
                template={editingTemplate}
                backendUrl={BACKEND_URL}
                onSave={() => {
                  setTemplateEditorState('list');
                  fetchData();
                }}
                onCancel={() => {
                  setTemplateEditorState('list');
                }}
              />
            )}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="glass-panel" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div className="panel-header">📑 Logs Operacionais da Linha de Produção (Histórico Completo)</div>
            <div className="panel-body" style={{ background: '#05070c', padding: '16px' }}>
              <LogsView logs={logs} />
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

