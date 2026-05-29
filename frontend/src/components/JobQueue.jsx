import React from 'react';

export default function JobQueue({ jobs, selectedJob, onSelectJob, onCreateMockJob }) {
  
  // Extract numerical progress if status contains 'Streaming: X%'
  const getStreamingProgress = (status) => {
    if (status && status.startsWith('Streaming')) {
      const match = status.match(/\d+/);
      return match ? parseInt(match[0], 10) : 0;
    }
    return 0;
  };

  return (
    <div className="panel-column glass-panel" style={{ height: '100%' }}>
      <div className="panel-header">
        <span>Fila de Lentes ({jobs.length})</span>
        <button 
          className="btn btn-glass" 
          style={{ padding: '4px 8px', fontSize: '0.65rem' }}
          onClick={onCreateMockJob}
        >
          + Teste OMA
        </button>
      </div>
      
      <div className="panel-body">
        {jobs.length === 0 ? (
          <div className="empty-state" style={{ padding: '16px' }}>
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            </svg>
            <p style={{ fontSize: '0.8rem' }}>Fila vazia. Insira um arquivo .oma na pasta "watch_dir" para iniciar.</p>
          </div>
        ) : (
          jobs.map((job) => {
            const isSelected = selectedJob && selectedJob.id === job.id;
            const progress = getStreamingProgress(job.status);
            const isStreaming = job.status.startsWith('Streaming');
            
            // Format status class name
            const statusClass = job.status.toLowerCase().replace(' ', '-').split(':')[0];
            
            return (
              <div 
                key={job.id} 
                className={`job-card ${isSelected ? 'active' : ''}`}
                onClick={() => onSelectJob(job)}
              >
                <div className="job-card-header">
                  <span style={{ color: '#fff' }}>
                    {job.job_id ? `ID: ${job.job_id}` : job.filename}
                  </span>
                  <span className={`job-status-tag status-${statusClass}`}>
                    {isStreaming ? `Gravação: ${progress}%` : job.status}
                  </span>
                </div>
                
                <div className="job-card-details">
                  <span>{job.lens_name || 'Lente Desconhecida'}</span>
                  <span>{job.eye === 'R' ? 'OD (Lente R)' : 'OS (Lente L)'}</span>
                </div>

                {isStreaming && (
                  <div className="progress-container">
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
