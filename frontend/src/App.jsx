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

const BACKEND_URL = 'http://localhost:8001';


export default function App() {
  const [jobs, setJobs] = useState([]);
  const [orders, setOrders] = useState([]);
  const [selectedOrderId, setSelectedOrderId] = useState(null);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [orderFlow, setOrderFlow] = useState(null);
  
  // Derive selected job from jobs array to avoid stale closures
  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null;
  const activeOrder = orders.find((o) => o.job_id === selectedOrderId) || null;

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

    // 3. Fetch Orders List
    fetch(`${BACKEND_URL}/api/orders`)
      .then((res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((data) => {
        setOrders(data);
        setBackendError(false);
      })
      .catch((err) => {
        console.error('Error fetching orders:', err);
      });

    // 4. Fetch System Logs
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

    // 5. Fetch Virtual Laser Machine status
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

  // Auto-select first order if none is selected
  useEffect(() => {
    if (!selectedOrderId && orders.length > 0) {
      setSelectedOrderId(orders[0].job_id);
    }
  }, [orders, selectedOrderId]);

  // Sync selectedJobId and orderFlow with active order
  useEffect(() => {
    if (!activeOrder) {
      setSelectedJobId(null);
      setOrderFlow(null);
      return;
    }
    setOrderFlow(activeOrder);
    
    // Determine active lens based on current state lens side
    const activeLens = activeOrder.current_lens || (activeOrder.od_job_id ? 'OD' : 'OE');
    if (activeLens === 'OE' && activeOrder.oe_job_id) {
      setSelectedJobId(activeOrder.oe_job_id);
    } else if (activeOrder.od_job_id) {
      setSelectedJobId(activeOrder.od_job_id);
    } else {
      setSelectedJobId(activeOrder.oe_job_id);
    }
  }, [activeOrder]);

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
        if (data.job_id) {
          setSelectedOrderId(data.job_id);
        }
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  // Handler to purge the entire database and reset simulator folders
  const handleClearAll = () => {
    if (!window.confirm("Aviso: Isso apagará permanentemente todos os pedidos, lentes do suporte e históricos de logs. Deseja prosseguir?")) {
      return;
    }
    fetch(`${BACKEND_URL}/api/system/clear-all`, { method: 'POST' })
      .then((res) => {
        if (res.ok) {
          setSelectedOrderId(null);
          setSelectedJobId(null);
          setOrderFlow(null);
          setJobs([]);
          setOrders([]);
          fetchData();
        } else {
          alert("Falha ao reiniciar o sistema.");
        }
      })
      .catch((err) => console.error(err));
  };

  // Guided Flow Event Handlers
  const handleStartFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/start`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handleConfirmRemoval = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/confirm-removal`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        if (data.oe_job_id && data.state === 'WAITING_LEFT_LENS') {
          setSelectedJobId(data.oe_job_id);
        }
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handleSkipFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/skip`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        if (data.oe_job_id && data.state === 'WAITING_LEFT_LENS') {
          setSelectedJobId(data.oe_job_id);
        }
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handlePauseFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/pause`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handleResumeFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/resume`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handleRestartFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/restart`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const handleCancelFlow = () => {
    if (!orderFlow) return;
    fetch(`${BACKEND_URL}/api/orders/${orderFlow.job_id}/flow/cancel`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setOrderFlow(data);
        fetchData();
      })
      .catch((err) => console.error(err));
  };

  const getStepIndex = (state) => {
    switch (state) {
      case 'WAITING_RIGHT_LENS': return 0;
      case 'RIGHT_LENS_PROCESSING': return 1;
      case 'WAITING_RIGHT_REMOVAL': return 2;
      case 'WAITING_LEFT_LENS': return 3;
      case 'LEFT_LENS_PROCESSING': return 4;
      case 'WAITING_LEFT_REMOVAL': return 5;
      case 'COMPLETED':
      case 'CANCELLED':
        return 6;
      case 'PAUSED':
      case 'ERROR':
        return orderFlow?.last_stopped_lens === 'OE' ? 4 : 1;
      default: return 0;
    }
  };

  const getInstructionText = (state) => {
    switch (state) {
      case 'WAITING_RIGHT_LENS':
        return 'Posicione a lente DIREITA (OD) no suporte de gravação e confirme para iniciar.';
      case 'RIGHT_LENS_PROCESSING':
        return 'Gravando lente DIREITA (OD). Acompanhe o progresso e o feixe laser.';
      case 'WAITING_RIGHT_REMOVAL':
        return 'Gravação da lente DIREITA (OD) concluída. Remova a lente do suporte e confirme a remoção.';
      case 'WAITING_LEFT_LENS':
        return 'Posicione a lente ESQUERDA (OE) no suporte de gravação e confirme para iniciar.';
      case 'LEFT_LENS_PROCESSING':
        return 'Gravando lente ESQUERDA (OE). Acompanhe o progresso e o feixe laser.';
      case 'WAITING_LEFT_REMOVAL':
        return 'Gravação da lente ESQUERDA (OE) concluída. Remova a lente do suporte.';
      case 'PAUSED':
        return `Gravação da Lente ${orderFlow?.last_stopped_lens || 'OD'} pausada pelo operador. Selecione uma ação para continuar.`;
      case 'ERROR':
        return 'ALERTA DE SISTEMA: O processo foi interrompido por um alarme de segurança ou falha de hardware.';
      case 'COMPLETED':
        return 'Ciclo de produção concluído com sucesso para este pedido!';
      case 'CANCELLED':
        return 'Este pedido foi cancelado manualmente e o ciclo foi abortado.';
      default:
        return 'Selecione um pedido na fila para iniciar o fluxo operacional.';
    }
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

  const isStreaming = selectedJob?.status.startsWith('Streaming') || machineStatus?.status === 'PROCESSING' || (orderFlow && (orderFlow.state === 'RIGHT_LENS_PROCESSING' || orderFlow.state === 'LEFT_LENS_PROCESSING'));
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
              <strong>ERRO DE CONEXÃO COM O SERVIDOR:</strong> O backend FastAPI (porta 8001) não está respondendo.
            </div>
          </div>
        )}

        {/* Dynamic Panel rendering */}
        {activeTab === 'production' && (
          <div className="dashboard-grid-scada">
            {/* Left Column: Queue & raw OMA parser */}
            <div className="panel-column-dense scada-queue-panel">
              <JobQueue 
                orders={orders} 
                selectedOrderId={selectedOrderId} 
                onSelectOrder={(orderId) => setSelectedOrderId(orderId)} 
                onCreateMockJob={handleCreateMockJob}
                onClearAll={handleClearAll}
                machineStatus={machineStatus}
              />
              <OMAViewer job={selectedJob} />
            </div>

            {/* Center Column: Lens Preview CAD & guided operational steps */}
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

              {/* Operator Guidance Workflow Panel */}
              {selectedJob && orderFlow && (
                <div className="operator-workflow-box" style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
                  {/* Production Stepper */}
                  <div className="production-stepper">
                    {[
                      'Posicionar OD',
                      'Gravando OD',
                      'Remover OD',
                      'Posicionar OE',
                      'Gravando OE',
                      'Remover OE',
                      'Concluído'
                    ].map((label, idx) => {
                      const activeIdx = getStepIndex(orderFlow.state);
                      let stepClass = 'stepper-step';
                      if (idx === activeIdx) {
                        stepClass += ' active';
                      } else if (idx < activeIdx) {
                        stepClass += ' completed';
                      }
                      return (
                        <div key={idx} className={stepClass}>
                          <div className="step-circle">
                            {idx < activeIdx ? '✓' : idx + 1}
                          </div>
                          <div className="step-label">{label}</div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Operator Instructions Box */}
                  <div className="operator-instructions-panel">
                    <div className="instruction-title">Orientação do Operador</div>
                    <div className="instruction-text">{getInstructionText(orderFlow.state)}</div>
                  </div>

                  {/* Operational Action Buttons */}
                  <div className="laser-control-actions" style={{ borderTop: 'none', padding: '12px 16px' }}>
                    {/* WAITING STATES */}
                    {(orderFlow.state === 'WAITING_RIGHT_LENS' || orderFlow.state === 'WAITING_LEFT_LENS') && (
                      <>
                        <button className="btn btn-cyan" onClick={handleStartFlow}>
                          ⚡ Iniciar Gravação
                        </button>
                        <button className="btn btn-glass" onClick={handleSkipFlow}>
                          ⏭️ Pular Lente
                        </button>
                        <button className="btn btn-glass" onClick={handleReprocessJob}>
                          🔄 Re-calcular Geometria
                        </button>
                      </>
                    )}

                    {/* PROCESSING STATES */}
                    {(orderFlow.state === 'RIGHT_LENS_PROCESSING' || orderFlow.state === 'LEFT_LENS_PROCESSING') && (
                      <>
                        <button className="btn btn-orange" onClick={handlePauseFlow}>
                          ⏸️ Pausar Gravação
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                      </>
                    )}

                    {/* PAUSED STATE */}
                    {orderFlow.state === 'PAUSED' && (
                      <>
                        <button className="btn btn-cyan" onClick={handleResumeFlow}>
                          ▶️ Retomar Gravação
                        </button>
                        <button className="btn btn-glass" onClick={handleRestartFlow}>
                          🔄 Reiniciar Lente
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                      </>
                    )}

                    {/* REMOVAL STATES */}
                    {orderFlow.state === 'WAITING_RIGHT_REMOVAL' && (
                      <button className="btn btn-green" onClick={handleConfirmRemoval}>
                        ✅ Confirmar Remoção
                      </button>
                    )}
                    {orderFlow.state === 'WAITING_LEFT_REMOVAL' && (
                      <button className="btn btn-green" onClick={handleConfirmRemoval}>
                        🏁 Finalizar Pedido
                      </button>
                    )}

                    {/* ERROR STATE */}
                    {orderFlow.state === 'ERROR' && (
                      <>
                        <button className="btn btn-orange" onClick={handleRestartFlow}>
                          🔄 Reiniciar Gravação
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                        <button className="btn btn-glass" onClick={handleResetAlarms} style={{ flex: 1.5 }}>
                          🔧 Resetar Alarme
                        </button>
                      </>
                    )}

                    {/* COMPLETED or CANCELLED STATE */}
                    {(orderFlow.state === 'COMPLETED' || orderFlow.state === 'CANCELLED') && (
                      <div style={{ display: 'flex', width: '100%', justifyContent: 'center', fontSize: '0.85rem', color: orderFlow.state === 'COMPLETED' ? 'var(--green-glow)' : 'var(--red-glow)', fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {orderFlow.state === 'COMPLETED' ? '✓ CICLO OPERACIONAL CONCLUÍDO' : '❌ CICLO OPERACIONAL CANCELADO'}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Right Column: Active Gcode console & order timeline */}
            <div className="panel-column-dense">
              <GcodePreview 
                gcodeText={gcodeText} 
                currentLineIndex={machineStatus.current_gcode_index}
                isStreaming={isStreaming}
              />
              
              {/* Order Specific Timeline */}
              <div className="glass-panel order-timeline-panel">
                <div className="panel-header" style={{ padding: '8px 12px', fontSize: '0.78rem' }}>
                  <span>📋 HISTÓRICO OPERACIONAL DO PEDIDO {orderFlow ? `: ${orderFlow.job_id}` : ''}</span>
                </div>
                <div className="timeline-list">
                  {orderFlow && orderFlow.logs && orderFlow.logs.length > 0 ? (
                    orderFlow.logs.map((log) => {
                      const logTime = new Date(log.timestamp).toLocaleTimeString('pt-BR');
                      const isWarning = log.event_type === 'ERROR' && log.message.includes('inatividade');
                      const isError = log.event_type === 'ERROR' && !log.message.includes('inatividade');
                      
                      let msgClass = "timeline-msg-text";
                      if (isWarning) msgClass += " warning";
                      if (isError) msgClass += " danger";
                      
                      return (
                        <div key={log.id} className="timeline-row">
                          <span className="timeline-time">{logTime}</span>
                          {log.lens_side && log.lens_side !== 'NONE' && (
                            <span className={`timeline-badge-tag badge-lens-${log.lens_side}`}>
                              {log.lens_side}
                            </span>
                          )}
                          <span className={`timeline-badge-tag badge-event-${log.event_type}`}>
                            {log.event_type}
                          </span>
                          <span className={msgClass}>{log.message}</span>
                        </div>
                      );
                    })
                  ) : (
                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                      [NENHUM EVENTO REGISTRADO]
                    </div>
                  )}
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
                orders={orders} 
                selectedOrderId={selectedOrderId} 
                onSelectOrder={(orderId) => setSelectedOrderId(orderId)} 
                onCreateMockJob={handleCreateMockJob}
                onClearAll={handleClearAll}
                machineStatus={machineStatus}
              />
            </div>

            {/* Center Column: Lens Preview CAD & guided operational steps */}
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

              {/* Operator Guidance Workflow Panel (Simulation Mode) */}
              {selectedJob && orderFlow && (
                <div className="operator-workflow-box" style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
                  {/* Production Stepper */}
                  <div className="production-stepper">
                    {[
                      'Posicionar OD',
                      'Gravando OD',
                      'Remover OD',
                      'Posicionar OE',
                      'Gravando OE',
                      'Remover OE',
                      'Concluído'
                    ].map((label, idx) => {
                      const activeIdx = getStepIndex(orderFlow.state);
                      let stepClass = 'stepper-step';
                      if (idx === activeIdx) {
                        stepClass += ' active';
                      } else if (idx < activeIdx) {
                        stepClass += ' completed';
                      }
                      return (
                        <div key={idx} className={stepClass}>
                          <div className="step-circle">
                            {idx < activeIdx ? '✓' : idx + 1}
                          </div>
                          <div className="step-label">{label}</div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Operator Instructions Box */}
                  <div className="operator-instructions-panel">
                    <div className="instruction-title">Orientação do Operador</div>
                    <div className="instruction-text">{getInstructionText(orderFlow.state)}</div>
                  </div>

                  {/* Operational Action Buttons */}
                  <div className="laser-control-actions" style={{ borderTop: 'none', padding: '12px 16px' }}>
                    {/* WAITING STATES */}
                    {(orderFlow.state === 'WAITING_RIGHT_LENS' || orderFlow.state === 'WAITING_LEFT_LENS') && (
                      <>
                        <button className="btn btn-cyan" onClick={handleStartFlow}>
                          ⚡ Iniciar Gravação
                        </button>
                        <button className="btn btn-glass" onClick={handleSkipFlow}>
                          ⏭️ Pular Lente
                        </button>
                        <button className="btn btn-glass" onClick={handleReprocessJob}>
                          🔄 Re-calcular Geometria
                        </button>
                      </>
                    )}

                    {/* PROCESSING STATES */}
                    {(orderFlow.state === 'RIGHT_LENS_PROCESSING' || orderFlow.state === 'LEFT_LENS_PROCESSING') && (
                      <>
                        <button className="btn btn-orange" onClick={handlePauseFlow}>
                          ⏸️ Pausar Gravação
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                      </>
                    )}

                    {/* PAUSED STATE */}
                    {orderFlow.state === 'PAUSED' && (
                      <>
                        <button className="btn btn-cyan" onClick={handleResumeFlow}>
                          ▶️ Retomar Gravação
                        </button>
                        <button className="btn btn-glass" onClick={handleRestartFlow}>
                          🔄 Reiniciar Lente
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                      </>
                    )}

                    {/* REMOVAL STATES */}
                    {orderFlow.state === 'WAITING_RIGHT_REMOVAL' && (
                      <button className="btn btn-green" onClick={handleConfirmRemoval}>
                        ✅ Confirmar Remoção
                      </button>
                    )}
                    {orderFlow.state === 'WAITING_LEFT_REMOVAL' && (
                      <button className="btn btn-green" onClick={handleConfirmRemoval}>
                        🏁 Finalizar Pedido
                      </button>
                    )}

                    {/* ERROR STATE */}
                    {orderFlow.state === 'ERROR' && (
                      <>
                        <button className="btn btn-orange" onClick={handleRestartFlow}>
                          🔄 Reiniciar Gravação
                        </button>
                        <button className="btn btn-red" onClick={handleCancelFlow}>
                          🛑 Cancelar Pedido
                        </button>
                        <button className="btn btn-glass" onClick={handleResetAlarms} style={{ flex: 1.5 }}>
                          🔧 Resetar Alarme
                        </button>
                      </>
                    )}

                    {/* COMPLETED or CANCELLED STATE */}
                    {(orderFlow.state === 'COMPLETED' || orderFlow.state === 'CANCELLED') && (
                      <div style={{ display: 'flex', width: '100%', justifyContent: 'center', fontSize: '0.85rem', color: orderFlow.state === 'COMPLETED' ? 'var(--green-glow)' : 'var(--red-glow)', fontWeight: 'bold', fontFamily: 'monospace' }}>
                        {orderFlow.state === 'COMPLETED' ? '✓ CICLO OPERACIONAL CONCLUÍDO' : '❌ CICLO OPERACIONAL CANCELADO'}
                      </div>
                    )}
                  </div>
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

