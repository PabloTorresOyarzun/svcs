from pathlib import Path
from litestar import Litestar, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.response import Template
from litestar.static_files import StaticFilesConfig

base_dir = Path(__file__).parent

# 1. Landing Page (PÃºblica)
@get(path="/")
async def index() -> Template:
    return Template(template_name="landing.html")

# 2. Login (AutenticaciÃ³n)
@get(path="/login")
async def login() -> Template:
    return Template(template_name="login.html")

# 3. Dashboard (Sistema Privado)
@get(path="/dashboard")
async def dashboard() -> Template:
    context = {
        "user_name": "Juan Pérez",
        "user_role": "Jefe de Operaciones",
        "alert_aduana": True,
        "alert_message": "Intermitencia en servicios de Aduana (SIDIV/DUS)"
    }
    return Template(template_name="dashboard.html", context=context)

# Rutas Placeholder
@get(path="/operaciones/despachos")
async def operaciones_view() -> Template:
    return Template(template_name="dashboard.html", context={"breadcrumbs": ["Operaciones", "Despachos"]})

@get(path="/finanzas/facturacion")
async def facturacion_view() -> Template:
    return Template(template_name="dashboard.html", context={"breadcrumbs": ["Finanzas", "FacturaciÃ³n"]})

app = Litestar(
    route_handlers=[index, login, dashboard, operaciones_view, facturacion_view],
    template_config=TemplateConfig(
        directory=base_dir / "templates",
        engine=JinjaTemplateEngine,
    ),
    static_files_config=[
        StaticFilesConfig(directories=[base_dir / "static"], path="/static"),
    ],
)