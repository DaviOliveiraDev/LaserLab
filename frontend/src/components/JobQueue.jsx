import React from 'react';

export default function JobQueue({ orders, selectedOrderId, onSelectOrder, onCreateMockJob, onClearAll, machineStatus }) {
  
  // Format status tag to PT-BR
  const formatStatusText = (status) => {
    switch (status) {
      case 'PENDING': return 'Pendente';
      case 'PROCESSING': return 'Gravando';
      case 'COMPLETED': return 'Pronto';
      case 'SKIPPED': return 'Pulado';
      case 'FAILED': return 'Falhou';
      default: return status;
    }
  };

  // Format order state for main card tag
  const formatOrderState = (state) => {
    switch (state) {
      case 'WAITING_RIGHT_LENS': return 'Aguardando OD';
      case 'RIGHT_LENS_PROCESSING': return 'Gravando OD';
      case 'WAITING_RIGHT_REMOVAL': return 'Remover OD';
      case 'WAITING_LEFT_LENS': return 'Aguardando OE';
      case 'LEFT_LENS_PROCESSING': return 'Gravando OE';
      case 'WAITING_LEFT_REMOVAL': return 'Remover OE';
      case 'COMPLETED': return 'Concluído';
      case 'CANCELLED': return 'Cancelado';
      case 'PAUSED': return 'Pausado';
      case 'ERROR': return 'Bloqueado';
      default: return state;
    }
  };

  // Calculate dynamic progress pct based on active machine telemetry
  const getStreamingProgress = (order) => {
    if (!machineStatus) return 0;
    if (order.state === 'RIGHT_LENS_PROCESSING' && machineStatus.current_job_id === order.od_job_id) {
      return Math.round(machineStatus.progress_pct);
    }
    if (order.state === 'LEFT_LENS_PROCESSING' && machineStatus.current_job_id === order.oe_job_id) {
      return Math.round(machineStatus.progress_pct);
    }
    return 0;
  };

  const getOrderStateClass = (state) => {
    if (state === 'COMPLETED') return 'status-success';
    if (state === 'CANCELLED' || state === 'ERROR') return 'status-failed';
    if (state.includes('PROCESSING')) return 'status-streaming';
    if (state === 'PAUSED') return 'status-calculating';
    return 'status-pending';
  };

  const renderLensStatus = (status, jobId, sideLabel) => {
    if (!jobId) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ fontWeight: '700', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{sideLabel}:</span>
          <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.65rem', fontFamily: 'monospace' }}>AUSENTE</span>
        </div>
      );
    }
    
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <span style={{ fontWeight: '700', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{sideLabel}:</span>
        <span className={`job-status-tag status-${status.toLowerCase()}`} style={{ fontSize: '0.6rem', padding: '1px 4px' }}>
          {formatStatusText(status)}
        </span>
      </div>
    );
  };

  return (
    <div className="panel-column glass-panel" style={{ height: '100%' }}>
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Fila de Pedidos ({orders.length})</span>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button 
            className="btn btn-glass" 
            style={{ padding: '4px 8px', fontSize: '0.65rem' }}
            onClick={onCreateMockJob}
          >
            + Teste OMA
          </button>
          <button 
            className="btn btn-red" 
            style={{ 
              padding: '4px 8px', 
              fontSize: '0.65rem', 
              background: 'rgba(239, 68, 68, 0.15)', 
              borderColor: 'rgba(239, 68, 68, 0.3)',
              color: '#ef4444'
            }}
            onClick={onClearAll}
          >
            🗑️ Limpar
          </button>
        </div>
      </div>
      
      <div className="panel-body">
        {orders.length === 0 ? (
          <div className="empty-state" style={{ padding: '16px' }}>
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="9" x2="15" y2="9" />
              <line x1="9" y1="13" x2="15" y2="13" />
              <line x1="9" y1="17" x2="11" y2="17" />
            </svg>
            <p style={{ fontSize: '0.8rem' }}>Fila vazia. Insira arquivos .oma para iniciar a produção.</p>
          </div>
        ) : (
          orders.map((order) => {
            const isSelected = selectedOrderId === order.job_id;
            const progress = getStreamingProgress(order);
            const isStreaming = order.state.includes('PROCESSING');
            
            return (
              <div 
                key={order.id} 
                className={`job-card ${isSelected ? 'active' : ''}`}
                onClick={() => onSelectOrder(order.job_id)}
                style={{ padding: '10px 12px', marginBottom: '8px' }}
              >
                <div className="job-card-header" style={{ marginBottom: '6px' }}>
                  <span style={{ color: '#fff', fontSize: '0.8rem', fontFamily: 'monospace' }}>
                    PEDIDO: {order.job_id}
                  </span>
                  <span className={`job-status-tag ${getOrderStateClass(order.state)}`}>
                    {formatOrderState(order.state)}
                  </span>
                </div>
                
                {/* Clearer OD and OE lens grid */}
                <div className="job-card-details" style={{ 
                  background: 'rgba(255,255,255,0.02)', 
                  padding: '6px 8px', 
                  borderRadius: '4px',
                  border: '1px solid rgba(255,255,255,0.03)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginTop: '4px'
                }}>
                  {renderLensStatus(order.od_status, order.od_job_id, 'OD (Dir.)')}
                  {renderLensStatus(order.oe_status, order.oe_job_id, 'OE (Esq.)')}
                </div>

                {isStreaming && progress > 0 && (
                  <div className="progress-container" style={{ marginTop: '8px', height: '4px' }}>
                    <div 
                      className="progress-bar" 
                      style={{ width: `${progress}%` }} 
                    />
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
