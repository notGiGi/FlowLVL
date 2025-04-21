<!-- Añadir al final del HTML, antes del cierre del body -->
<style>
/* Estilos para línea temporal */
.timeline-container {
    margin: 20px 0;
    padding: 20px 0;
}

.timeline-track {
    position: relative;
    height: 8px;
    background-color: #e9ecef;
    border-radius: 4px;
    margin: 30px 0;
}

.timeline-point-container {
    position: absolute;
    transform: translateX(-50%);
}

.timeline-point {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    position: relative;
    top: -4px;
    cursor: pointer;
}

.timeline-label {
    position: absolute;
    top: 15px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 12px;
    white-space: nowrap;
}

.bg-purple {
    background-color: #6f42c1;
}
</style>

<script>
// Función para cargar datos de predicción de línea temporal
function loadPredictionTimeline(serviceId) {
    fetch(`/api/predict/${serviceId}?hours=24`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error("Error al obtener predicciones:", data.error);
                return;
            }
            
            // Mostrar línea temporal
            renderTimeline(data);
            
            // Llenar tabla de métricas
            populateTimelineTable(data);
        })
        .catch(error => console.error("Error al cargar predicciones:", error));
}

// Función para renderizar línea temporal
function renderTimeline(data) {
    const timelineEl = document.getElementById('predictionTimeline');
    if (!timelineEl) return; // No existe el elemento
    
    timelineEl.innerHTML = '';
    
    if (!data.timeline) {
        timelineEl.innerHTML = '<div class="alert alert-info">No hay suficientes datos para generar predicciones</div>';
        return;
    }
    
    // Crear elementos de línea temporal
    const timeIntervals = Object.keys(data.timeline).sort((a, b) => parseInt(a) - parseInt(b));
    
    let timelineHtml = '<div class="timeline-track">';
    
    timeIntervals.forEach(hours => {
        const timePoint = data.timeline[hours];
        const now = new Date();
        const futureTime = new Date(now.getTime() + (parseInt(hours) * 60 * 60 * 1000));
        const timeLabel = futureTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        let pointClass = 'timeline-point';
        let statusClass = '';
        let tooltip = `${hours}h: ${timeLabel}`;
        
        if (timePoint.highest_severity > 0.7) {
            statusClass = 'danger';
            tooltip += ' - Anomalía crítica prevista';
        } else if (timePoint.highest_severity > 0.4) {
            statusClass = 'warning';
            tooltip += ' - Posible anomalía';
        } else {
            statusClass = 'success';
            tooltip += ' - Normal';
        }
        
        timelineHtml += `
            <div class="timeline-point-container" style="left: ${(parseInt(hours)/24)*100}%">
                <div class="timeline-point bg-${statusClass}" title="${tooltip}"></div>
                <div class="timeline-label">${hours}h</div>
            </div>
        `;
    });
    
    timelineHtml += '</div>';
    
    // Añadir información de primera anomalía si existe
    if (data.first_anomaly_in !== null) {
        const anomalyTime = new Date();
        anomalyTime.setHours(anomalyTime.getHours() + data.first_anomaly_in);
        
        timelineHtml += `
            <div class="alert alert-warning mt-3">
                <strong>⚠️ Primera anomalía prevista:</strong> en ${data.first_anomaly_in} horas 
                (${anomalyTime.toLocaleString()})
                <div class="progress mt-2">
                    <div class="progress-bar bg-danger" role="progressbar" 
                         style="width: ${data.probability * 100}%" 
                         aria-valuenow="${data.probability * 100}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                        Probabilidad: ${(data.probability * 100).toFixed(1)}%
                    </div>
                </div>
                <div class="mt-2">
                    <small>Confianza en la predicción: ${(data.confidence * 100).toFixed(1)}%</small>
                </div>
            </div>
        `;
    } else {
        timelineHtml += `
            <div class="alert alert-success mt-3">
                <strong>✅ No se prevén anomalías</strong> en las próximas 24 horas.
            </div>
        `;
    }
    
    timelineEl.innerHTML = timelineHtml;
}

// Función para llenar tabla de métricas por intervalo
function populateTimelineTable(data) {
    const tableBody = document.querySelector('#timelineTable tbody');
    if (!tableBody) return; // No existe el elemento
    
    tableBody.innerHTML = '';
    
    if (!data.timeline || Object.keys(data.timeline).length === 0) {
        return;
    }
    
    // Obtener todas las métricas únicas
    const allMetrics = new Set();
    for (const time in data.timeline) {
        for (const metric in data.timeline[time].metrics) {
            allMetrics.add(metric);
        }
    }
    
    // Crear filas para cada métrica
    allMetrics.forEach(metric => {
        let row = `<tr><td><strong>${metric}</strong></td>`;
        
        // Columnas para cada intervalo de tiempo
        const timeIntervals = ["1", "2", "4", "8", "12", "24"];
        
        timeIntervals.forEach(time => {
            const value = data.timeline[time]?.metrics[metric];
            
            if (value !== undefined) {
                // Verificar si es anomalía
                let cellClass = '';
                const anomaly = data.timeline[time]?.anomalies?.find(a => a.metric === metric);
                
                if (anomaly) {
                    cellClass = anomaly.severity > 0.7 ? 'table-danger' : 'table-warning';
                }
                
                row += `<td class="${cellClass}">${value.toFixed(2)}</td>`;
            } else {
                row += '<td>—</td>';
            }
        });
        
        row += '</tr>';
        tableBody.innerHTML += row;
    });
}

// Añadir evento para cargar línea temporal al seleccionar servicio
document.addEventListener('DOMContentLoaded', function() {
    // Añadir al botón de detalles
    document.querySelectorAll('.service-details').forEach(button => {
        const originalOnClick = button.onclick;
        button.onclick = function() {
            const serviceId = this.getAttribute('data-id');
            if (originalOnClick) originalOnClick.call(this);
            setTimeout(() => loadPredictionTimeline(serviceId), 500);
        };
    });
    
    // Añadir automáticamente en la página de inicio
    setTimeout(() => {
        const firstService = document.querySelector('.service-details');
        if (firstService) {
            const serviceId = firstService.getAttribute('data-id');
            loadPredictionTimeline(serviceId);
        }
    }, 1000);
});
</script>