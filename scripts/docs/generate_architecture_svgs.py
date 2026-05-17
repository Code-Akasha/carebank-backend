from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(r"d:\PycharmProjects\carebank-backend\docs\architecture-diagrams")

WHITE = "#FFFFFF"
TITLE = "#0F172A"
TEXT = "#1F2937"
MUTED = "#475569"
LINE = "#334155"
BLUE = "#DBEAFE"
BLUE_STROKE = "#3B82F6"
GREEN = "#DCFCE7"
GREEN_STROKE = "#16A34A"
AMBER = "#FEF3C7"
AMBER_STROKE = "#D97706"
PINK = "#FCE7F3"
PINK_STROKE = "#DB2777"
GRAY = "#F8FAFC"
GRAY_STROKE = "#CBD5E1"


def get_font(
    size: int, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ("C:/Windows/Fonts/aptos.ttf", False),
        ("C:/Windows/Fonts/aptosb.ttf", True),
        ("C:/Windows/Fonts/segoeui.ttf", False),
        ("C:/Windows/Fonts/segoeuib.ttf", True),
        ("C:/Windows/Fonts/arial.ttf", False),
        ("C:/Windows/Fonts/arialbd.ttf", True),
    ]
    for path, is_bold in candidates:
        if is_bold != bold:
            continue
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


FONT_26B = get_font(26, True)
FONT_19B = get_font(19, True)
FONT_17B = get_font(17, True)
FONT_14 = get_font(14, False)
FONT_13 = get_font(13, False)
FONT_12 = get_font(12, False)
FONT_11B = get_font(11, True)


def wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class Canvas:
    def __init__(self, width: int, height: int, title: str):
        self.image = Image.new("RGB", (width, height), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.width = width
        self.height = height
        self.draw.text((width // 2, 36), title, font=FONT_26B, fill=TITLE, anchor="mm")

    def section(
        self, x: int, y: int, w: int, h: int, title: str, subtitle: str
    ) -> None:
        self.draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=22, outline=GRAY_STROKE, width=3, fill=GRAY
        )
        self.draw.text((x + 18, y + 20), title, font=FONT_19B, fill=TITLE)
        self.draw.text((x + 18, y + 48), subtitle, font=FONT_12, fill=MUTED)

    def box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        bullets: list[str],
        fill: str,
        stroke: str,
    ) -> None:
        self.draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=18, outline=stroke, width=3, fill=fill
        )
        self.draw.text(
            (x + w / 2, y + 24), title, font=FONT_17B, fill=TITLE, anchor="mm"
        )
        yy = y + 50
        for bullet in bullets:
            lines = wrap(self.draw, bullet, FONT_13, w - 30)
            for line in lines:
                self.draw.text((x + 15, yy), line, font=FONT_13, fill=TEXT)
                yy += 18
            yy += 2

    def arrow(self, x1: int, y1: int, x2: int, y2: int, label: str = "") -> None:
        self.draw.line((x1, y1, x2, y2), fill=LINE, width=3)
        self._arrowhead(x1, y1, x2, y2)
        if label:
            lx = (x1 + x2) / 2
            ly = (y1 + y2) / 2 - 12
            tw = self.draw.textlength(label, font=FONT_11B)
            self.draw.rounded_rectangle(
                (lx - tw / 2 - 10, ly - 6, lx + tw / 2 + 10, ly + 14),
                radius=10,
                fill=WHITE,
            )
            self.draw.text((lx, ly + 4), label, font=FONT_11B, fill=MUTED, anchor="mm")

    def note(self, x: int, y: int, text: str, width: int) -> None:
        yy = y
        for line in wrap(self.draw, text, FONT_12, width):
            self.draw.text((x, yy), line, font=FONT_12, fill=MUTED)
            yy += 16

    def _arrowhead(self, x1: int, y1: int, x2: int, y2: int) -> None:
        import math

        angle = math.atan2(y2 - y1, x2 - x1)
        size = 10
        a1 = angle + math.pi * 0.85
        a2 = angle - math.pi * 0.85
        p1 = (x2, y2)
        p2 = (x2 + size * math.cos(a1), y2 + size * math.sin(a1))
        p3 = (x2 + size * math.cos(a2), y2 + size * math.sin(a2))
        self.draw.polygon([p1, p2, p3], fill=LINE)

    def save(self, name: str) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        self.image.save(OUT_DIR / name, format="PNG")


def overall() -> None:
    c = Canvas(1400, 900, "CareBank Overall System Architecture")
    c.section(
        60,
        90,
        1280,
        740,
        "End-to-End Platform",
        "Frontend, backend, MockBank, data stores, and provider integrations",
    )
    c.box(
        110,
        190,
        250,
        180,
        "Frontend",
        [
            "React + Vite UI",
            "JWT login/session",
            "Dashboard, chat, planning",
            "Notifications and MPIN UX",
            "Optional SSE stream",
        ],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        420,
        140,
        330,
        270,
        "CareBank Backend",
        [
            "FastAPI routes and auth",
            "Coordinator + specialist agents",
            "Deterministic finance core",
            "Compliance guard",
            "Action engine + planning",
            "Admin and observability",
        ],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        810,
        190,
        250,
        180,
        "MockBank",
        [
            "Balances and transactions",
            "Policies and rail caps",
            "Products, schedules",
            "Beneficiaries and transfers",
            "Lifecycle webhooks",
        ],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        1110,
        190,
        190,
        180,
        "LLM Providers",
        ["OpenAI / Gemini", "Optional Ollama", "Text tasks only"],
        PINK,
        PINK_STROKE,
    )
    c.box(
        430,
        520,
        220,
        140,
        "Postgres",
        ["Users, plans, actions", "sessions, audit logs", "transactions, pgvector"],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        720,
        520,
        220,
        140,
        "Redis",
        ["Pub/Sub events", "SSE fanout", "Worker queue path"],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        1010,
        520,
        280,
        140,
        "Webhook / Event Path",
        [
            "Queued, running, success",
            "failure, rollback",
            "Signed callback + reconcile",
        ],
        AMBER,
        AMBER_STROKE,
    )
    c.arrow(360, 280, 420, 280, "JWT API calls")
    c.arrow(750, 280, 810, 280, "Service JWT")
    c.arrow(1060, 280, 1110, 280, "NLG / classify")
    c.arrow(585, 410, 540, 520, "Persist")
    c.arrow(650, 410, 760, 520, "Publish")
    c.arrow(935, 370, 1070, 520, "Lifecycle")
    c.arrow(720, 680, 250, 680, "UI responses and SSE")
    c.save("01-overall-system.png")


def backend() -> None:
    c = Canvas(1500, 980, "CareBank Backend Architecture")
    c.section(
        60,
        90,
        1380,
        850,
        "Backend Layers",
        "FastAPI, orchestration, services, safety, persistence, and integrations",
    )
    c.box(
        100,
        150,
        270,
        630,
        "HTTP / API Layer",
        [
            "Routes for auth, chat, actions",
            "planning, transactions, products",
            "notifications, admin, bot",
            "balances, schedules, profile",
        ],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        430,
        150,
        250,
        190,
        "Coordinator Agent",
        [
            "Intent classification",
            "Task planning",
            "LangGraph state",
            "Response synthesis",
        ],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        430,
        390,
        250,
        250,
        "Specialist Agents",
        [
            "Intelligence",
            "Opportunity",
            "Communication",
            "Auto-savings",
            "Tool registry",
        ],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        740,
        130,
        300,
        220,
        "Deterministic and Safety Core",
        [
            "Finance calculations",
            "Affordability and health score",
            "Compliance guard",
            "Redaction and disclosures",
        ],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        740,
        400,
        300,
        270,
        "Business Services",
        [
            "Action executor and policy",
            "Action request + idempotency",
            "Banking client",
            "Forecast, anomaly, NLG",
            "Planning and reminders",
            "Event dispatcher, MPIN",
        ],
        PINK,
        PINK_STROKE,
    )
    c.box(
        1100,
        170,
        270,
        180,
        "External Integrations",
        ["MockBank API", "Telegram webhook", "LLM providers"],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        1100,
        430,
        270,
        180,
        "Persistence and Events",
        [
            "Postgres models",
            "Redis Pub/Sub and SSE",
            "Audit trail",
            "Worker path planned",
        ],
        BLUE,
        BLUE_STROKE,
    )
    c.arrow(370, 250, 430, 240, "Validated request")
    c.arrow(555, 340, 555, 390, "Route tasks")
    c.arrow(680, 240, 740, 240, "Exact math")
    c.arrow(680, 520, 740, 520, "Service calls")
    c.arrow(890, 350, 890, 400, "Policy + state")
    c.arrow(1040, 250, 1100, 250, "Outbound APIs")
    c.arrow(1040, 520, 1100, 520, "Read / write")
    c.arrow(1235, 350, 1235, 430, "Events")
    c.arrow(1100, 700, 370, 700, "Responses / streams")
    c.save("02-backend-architecture.png")


def frontend() -> None:
    c = Canvas(1400, 860, "CareBank Frontend Architecture")
    c.section(
        60,
        90,
        1280,
        700,
        "Client Application",
        "Web UI structure and integration with the backend",
    )
    c.box(
        100,
        220,
        220,
        150,
        "Entry Shell",
        ["Vite bootstrap", "Navigation shell", "Environment config"],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        390,
        150,
        260,
        190,
        "Authentication UX",
        ["Login / onboarding", "JWT storage", "MPIN setup / verify"],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        390,
        400,
        260,
        230,
        "Feature Screens",
        [
            "Dashboard and health",
            "Chat and recommendations",
            "Simulation",
            "Planning / checklist",
            "Transactions and alerts",
        ],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        720,
        150,
        280,
        190,
        "API Client Layer",
        ["REST calls to backend", "JWT headers", "Response normalization"],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        720,
        410,
        280,
        170,
        "Realtime Updates",
        ["Optional EventSource/SSE", "Live nudges", "Notification refresh"],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        1080,
        260,
        220,
        200,
        "CareBank Backend",
        ["Auth", "Chat", "Planning", "Actions", "Events"],
        PINK,
        PINK_STROKE,
    )
    c.arrow(320, 295, 390, 245, "Boot / auth")
    c.arrow(320, 295, 390, 500, "Route to screens")
    c.arrow(650, 245, 720, 245, "JWT REST")
    c.arrow(650, 500, 720, 480, "Feature data")
    c.arrow(1000, 245, 1080, 315, "REST")
    c.arrow(1000, 490, 1080, 390, "SSE")
    c.arrow(1080, 440, 650, 610, "Push updates")
    c.note(
        100,
        710,
        "Frontend repo was not available in this workspace, so this diagram reflects the interfaces documented in the backend architecture and the open IDE context.",
        1180,
    )
    c.save("03-frontend-architecture.png")


def mockbank() -> None:
    c = Canvas(1450, 900, "MockBank Architecture")
    c.section(
        60,
        90,
        1330,
        740,
        "Banking Simulation Layer",
        "Execution, policies, lifecycle states, and webhook delivery",
    )
    c.box(
        100,
        280,
        220,
        150,
        "CareBank Backend",
        ["Trusted client", "Short-lived service JWT", "Fetches and actions"],
        BLUE,
        BLUE_STROKE,
    )
    c.box(
        390,
        150,
        300,
        220,
        "MockBank API",
        [
            "Accounts and balances",
            "Transactions and products",
            "Beneficiaries and schedules",
            "Transfer trigger endpoints",
        ],
        AMBER,
        AMBER_STROKE,
    )
    c.box(
        390,
        470,
        300,
        220,
        "Policy Engine",
        [
            "Rail limits and action caps",
            "Verification and cooldowns",
            "Funds checks",
            "Idempotency enforcement",
        ],
        GREEN,
        GREEN_STROKE,
    )
    c.box(
        760,
        150,
        280,
        220,
        "Transaction Lifecycle",
        [
            "queued -> running -> success",
            "failure / reversal",
            "Settlement metadata",
            "Replay-safe ids",
        ],
        PINK,
        PINK_STROKE,
    )
    c.box(
        760,
        470,
        280,
        220,
        "Webhook Delivery",
        [
            "HMAC signed callbacks",
            "Retry with backoff",
            "Dead-letter replay path",
            "Backend reconciliation",
        ],
        PINK,
        PINK_STROKE,
    )
    c.box(
        1110,
        300,
        220,
        210,
        "MockBank Storage",
        [
            "Current mock persistence",
            "Schedules",
            "Beneficiaries",
            "Dead-letter records",
            "Postgres path planned",
        ],
        BLUE,
        BLUE_STROKE,
    )
    c.arrow(320, 355, 390, 270, "Fetch / execute")
    c.arrow(540, 370, 540, 470, "Validate")
    c.arrow(690, 260, 760, 260, "Approved txn")
    c.arrow(690, 580, 760, 580, "Emit webhook")
    c.arrow(1040, 260, 1110, 340, "Persist")
    c.arrow(1040, 580, 1110, 460, "Retry / dead-letter")
    c.arrow(760, 620, 320, 390, "Signed callback")
    c.save("04-mockbank-architecture.png")


def flow() -> None:
    c = Canvas(1600, 950, "CareBank Operational Flow")
    c.section(
        60,
        90,
        1480,
        800,
        "Transaction-to-Nudge and Action Flow",
        "How events, analysis, approval, execution, and user updates move through the system",
    )
    items = [
        (
            110,
            220,
            "1. User or Bank Event",
            ["App request or new", "bank transaction arrives"],
            BLUE,
            BLUE_STROKE,
        ),
        (
            380,
            220,
            "2. Backend Intake",
            ["JWT validated", "user_id scoped", "request routed"],
            GREEN,
            GREEN_STROKE,
        ),
        (
            650,
            220,
            "3. Coordinator Planning",
            ["Intent classified", "tasks decomposed", "agent path chosen"],
            GREEN,
            GREEN_STROKE,
        ),
        (
            920,
            220,
            "4. Data Retrieval",
            ["Fetch balances,", "transactions, products,", "policies"],
            AMBER,
            AMBER_STROKE,
        ),
        (
            1190,
            220,
            "5. Analysis Layer",
            ["Forecasting / anomaly", "deterministic math"],
            PINK,
            PINK_STROKE,
        ),
        (
            1190,
            560,
            "6. Decision Output",
            ["Nudge, warning,", "plan, or proposal"],
            BLUE,
            BLUE_STROKE,
        ),
        (
            920,
            560,
            "7. Approval Gate",
            ["Ask user or apply", "policy threshold"],
            AMBER,
            AMBER_STROKE,
        ),
        (
            650,
            560,
            "8. Action Execution",
            ["Action engine triggers", "MockBank transfer"],
            GREEN,
            GREEN_STROKE,
        ),
        (
            380,
            560,
            "9. Webhook Reconcile",
            ["Signed lifecycle", "updates reconciled"],
            PINK,
            PINK_STROKE,
        ),
        (
            110,
            560,
            "10. User Update",
            ["REST/SSE response", "audit trail persisted"],
            BLUE,
            BLUE_STROKE,
        ),
    ]
    for x, y, title, lines, fill, stroke in items:
        c.box(x, y, 220, 120, title, lines, fill, stroke)
    c.arrow(330, 280, 380, 280)
    c.arrow(600, 280, 650, 280)
    c.arrow(870, 280, 920, 280)
    c.arrow(1140, 280, 1190, 280)
    c.arrow(1300, 340, 1300, 560, "Decision")
    c.arrow(1190, 620, 1140, 620)
    c.arrow(920, 620, 870, 620)
    c.arrow(650, 620, 600, 620)
    c.arrow(380, 620, 330, 620)
    c.note(
        970,
        760,
        "If no action is required, the system can return from step 6 directly to the user with advice only. If approval is needed, the action engine pauses at step 7 until the user confirms.",
        500,
    )
    c.save("05-operational-flow.png")


def main() -> None:
    overall()
    backend()
    frontend()
    mockbank()
    flow()


if __name__ == "__main__":
    main()
