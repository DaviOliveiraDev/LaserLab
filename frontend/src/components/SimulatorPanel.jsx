import React from 'react';

export default function SimulatorPanel({ 
  machineStatus, 
  onTriggerAlarm, 
  onResetAlarms, 
  onCreateMockJob,
  backendUrl 
}) {
  if (!machineStatus) {
    return (
      <div className="glass-panel" style={{ padding: '20px', display: 'flex', justifyContent: 'center' }}>
        <span>Carregando dados do simulador PLC...</span>
      </div>
    );
  }

  const {
    status,
    temperature,
    laser_power_w,
    safety_door_locked,
    door_open_alarm,
    overtemp_alarm,
    power_drop_alarm,
    current_job_id,
    progress_pct
  } = machineStatus;

  const hasAlarms = door_open_alarm || overtemp_alarm || power_drop_alarm;

  return (
    <div className="panel-column glass-panel simulator-panel-container">
      <div className="panel-header">
        <span>⚙️ PAINEL PLC & INJEÇÃO DE FALHAS DO SIMULADOR</span>
      </div>

      <div className="panel-body flex-column" style={{ gap: '16px' }}>
        
        {/* Status indicator row */}
        <div className="simulator-status-grid">
          <div className={`simulator-card telemetry-card ${status === 'ERROR' ? 'card-danger blink-danger-border' : ''}`}>
            <span className="card-label">ESTADO CLP</span>
            <span className={`card-value text-glow-${status === 'ERROR' ? 'red' : status === 'PROCESSING' ? 'orange' : 'green'}`}>
              {status}
            </span>
          </div>

          <div className="simulator-card telemetry-card">
            <span className="card-label">TEMP DIODO</span>
            <span className={`card-value ${temperature > 60 ? 'text-danger' : temperature > 40 ? 'text-warning' : ''}`}>
              {temperature.toFixed(1)} °C
            </span>
            <span className="card-sub-label">Threshold: 65°C</span>
          </div>

          <div className="simulator-card telemetry-card">
            <span className="card-label">POTÊNCIA LASER</span>
            <span className="card-value text-cyan">
              {laser_power_w.toFixed(1)} W
            </span>
            <span className="card-sub-label">Nominal: 25.0W</span>
          </div>

          <div className="simulator-card telemetry-card">
            <span className="card-label">TRAVA PORTA</span>
            <span className={`card-value ${safety_door_locked ? 'text-success' : 'text-danger'}`}>
              {safety_door_locked ? 'TRAVADA' : 'ABERTA'}
            </span>
          </div>
        </div>

        {/* Warning Indicator Overlay if alarms active */}
        {hasAlarms && (
          <div className="industrial-alert-box alert-danger">
            <span className="alert-icon">⚠️</span>
            <div className="alert-content">
              <strong>FALHA DE SEGURANÇA DETECTADA:</strong>
              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                {door_open_alarm && <li>Enclosure Door Open (G-code stream blocked)</li>}
                {overtemp_alarm && <li>Laser Diode Over-Temperature Threshold Exceeded (&gt;65.0°C)</li>}
                {power_drop_alarm && <li>Diode Degradation / Optical Power Drop Detected</li>}
              </ul>
            </div>
          </div>
        )}

        {/* Alarm Injection Controls */}
        <div className="control-section-title">🔌 SIMULAÇÃO DE HARDWARE INTERRUPT</div>
        <div className="alarm-injectors-grid">
          
          {/* Switch 1: Enclosure Door */}
          <button 
            className={`btn alarm-btn ${door_open_alarm ? 'btn-red-active' : 'btn-glass'}`}
            onClick={() => onTriggerAlarm('door_open', !door_open_alarm)}
          >
            🚪 {door_open_alarm ? 'FECHAR PORTA' : 'ABRIR PORTA DE SEGURANÇA'}
          </button>

          {/* Switch 2: Diode Overtemp */}
          <button 
            className={`btn alarm-btn ${overtemp_alarm ? 'btn-red-active' : 'btn-glass'}`}
            onClick={() => onTriggerAlarm('overtemp', !overtemp_alarm)}
          >
            🔥 {overtemp_alarm ? 'RESFRIAR DIODO' : 'FORÇAR SOBREAQUECIMENTO'}
          </button>

          {/* Switch 3: Power Drop */}
          <button 
            className={`btn alarm-btn ${power_drop_alarm ? 'btn-red-active' : 'btn-glass'}`}
            onClick={() => onTriggerAlarm('power_drop', !power_drop_alarm)}
          >
            ⚡ {power_drop_alarm ? 'NORMALIZAR ENERGIA' : 'SIMULAR QUEDA DE POTÊNCIA'}
          </button>
        </div>

        {/* Interactive Reset Actions */}
        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
          <button 
            className="btn btn-green"
            onClick={onResetAlarms}
            disabled={!hasAlarms && status !== 'ERROR'}
            style={{ flex: 1 }}
          >
            ✅ RESETAR INTERTRAVAMENTOS CLP
          </button>
          
          <button 
            className="btn btn-glass"
            onClick={onCreateMockJob}
            style={{ flex: 1 }}
          >
            📁 INJETAR ARQUIVO OMA (.OMA)
          </button>
        </div>

        <div className="sensor-disclaimer">
          <span>* O painel acima simula registradores físicos de um Controlador Lógico Programável (CLP/PLC) conectado à placa galvo. Injeções de falha forçam paradas de emergência instantâneas em conformidade com a norma NR-12.</span>
        </div>

      </div>
    </div>
  );
}
