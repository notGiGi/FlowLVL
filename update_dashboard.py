# -*- coding: utf-8 -*-
import re

# Leer el archivo HTML
with open("./templates/index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Cambiar el título del sistema
html_content = html_content.replace("<title>Sistema de Mantenimiento Predictivo</title>", 
                                  "<title>Dashboard de Predicción Proactiva AI</title>")

# Cambiar el nombre en la barra de navegación
html_content = html_content.replace('<a class="navbar-brand" href="#">Sistema de Mantenimiento Predictivo</a>', 
                                  '<a class="navbar-brand" href="#">Dashboard de Predicción Proactiva AI</a>')

# Cambiar el título del dashboard principal
html_content = html_content.replace("<h2>Estado del Sistema</h2>", 
                                  "<h2>Centro de Control Predictivo AI</h2>")

# Añadir estilos para el tema de IA
styles = """
<style>
/* Estilos adicionales para dashboard de IA */
.navbar-brand:before {
    content: "🧠";
    margin-right: 8px;
}

.ai-badge {
    background-color: #6f42c1;
    color: white;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
    margin-left: 8px;
    vertical-align: middle;
}

.prediction-title {
    color: #6f42c1;
    font-weight: bold;
}

.ai-icon {
    font-size: 20px;
    vertical-align: middle;
    margin-right: 5px;
}
</style>
"""

# Añadir estilos al head
html_content = html_content.replace("</head>", f"{styles}</head>")

# Buscar y reemplazar los títulos de predicción con versiones con badges
if "<h3>Predicción Proactiva</h3>" in html_content:
    html_content = html_content.replace("<h3>Predicción Proactiva</h3>", 
                                       "<h3 class='prediction-title'><span class='ai-icon'>🧠</span>Predicción Proactiva<span class='ai-badge'>AI</span></h3>")

# Buscar y reemplazar el título de línea temporal
line_title_pattern = re.compile(r'<h4 class="mb-0">Línea temporal de predicciones</h4>')
html_content = line_title_pattern.sub('<h4 class="mb-0">Línea temporal de predicciones<span class=\'ai-badge\'>AI</span></h4>', html_content)

# Guardar el archivo actualizado
with open("./templates/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("✅ Dashboard actualizado con éxito")