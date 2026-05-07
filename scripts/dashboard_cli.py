from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import jwt
from rich import box
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

BACKEND_URL = os.getenv("CAREBANK_BACKEND_URL", "http://localhost:8000")
PROXY_URL = os.getenv("CAREBANK_PROXY_URL", "http://localhost:8001")
JWT_SECRET = os.getenv("CAREBANK_PROXY_JWT_SECRET", "mockbank-dev-secret")

MENU_OPTIONS = {
    "1": ("System health check", "show_status"),
    "2": ("View balance", "view_balance"),
    "3": ("List transactions", "list_transactions"),
    "4": ("Run health score", "run_health_score"),
    "5": ("Simulate expense", "simulate_expense"),
    "6": ("Trigger transaction", "trigger_transaction"),
    "7": ("Trigger admin scenario", "trigger_scenario"),
    "8": ("Upsert proxy profile", "upsert_profile"),
    "9": ("Watch live events", "watch_events"),
    "10": ("View accounts", "view_accounts"),
    "11": ("List providers", "list_providers"),
    "0": ("Exit", "exit_app"),
}


class Dashboard:
    def __init__(self) -> None:
        self.backend_url = BACKEND_URL.rstrip("/")
        self.proxy_url = PROXY_URL.rstrip("/")
        self.http_timeout = httpx.Timeout(15.0, connect=5.0)

    def run(self) -> None:
        console.print("[bold cyan]\nCareBank Ops Dashboard[/bold cyan]")
        console.print("Backend: [yellow]{}[/yellow]".format(self.backend_url))
        console.print("Proxy: [yellow]{}[/yellow]\n".format(self.proxy_url))

        while True:
            for key, (label, _) in MENU_OPTIONS.items():
                console.print(f"[{key}] {label}")
            choice = Prompt.ask("Select an option", choices=list(MENU_OPTIONS.keys()))
            action = getattr(self, MENU_OPTIONS[choice][1])
            try:
                action()
            except KeyboardInterrupt:
                console.print("\n[red]Cancelled[/red]\n")
            except httpx.HTTPError as exc:
                console.print(f"[red]HTTP error:[/red] {exc}")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Unexpected error:[/red] {exc}")

    def show_status(self) -> None:
        backend = self._request_backend("GET", "/")
        proxy = self._request_proxy(
            "GET", "/", token=self._user_token("user_001")
        )
        table = Table(title="Service Health", box=box.SIMPLE)
        table.add_column("Service")
        table.add_column("Status")
        table.add_row("Backend", json.dumps(backend))
        table.add_row("Proxy", json.dumps(proxy))
        console.print(table)

    def view_balance(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        data = self._request_backend("GET", f"/api/balances/{user_id}")
        table = Table(title=f"Balance for {user_id}", box=box.SIMPLE)
        table.add_column("Current", justify="right")
        table.add_column("Available", justify="right")
        table.add_column("Updated")
        table.add_row(
            f"₹{data['current_balance']:,.2f}",
            f"₹{data['available_balance']:,.2f}",
            data.get("last_updated", "n/a"),
        )
        console.print(table)

    def list_transactions(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        params = {"user_id": user_id, "limit": 10}
        records = self._request_backend("GET", "/api/transactions", params=params)
        if not records:
            console.print("[yellow]No transactions found.[/yellow]")
            return
        table = Table(title=f"Recent transactions for {user_id}", box=box.SIMPLE)
        table.add_column("Date")
        table.add_column("Merchant")
        table.add_column("Category")
        table.add_column("Amount", justify="right")
        for txn in records[:20]:
            ts = txn.get("date")
            ts_str = ts if isinstance(ts, str) else str(ts)
            table.add_row(
                ts_str[:19],
                txn.get("merchant", "-"),
                txn.get("category", "-"),
                f"₹{txn['amount']:,.2f}",
            )
        console.print(table)

    def run_health_score(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        data = self._request_backend("GET", f"/api/health-score/{user_id}")
        table = Table(title=f"Health Score for {user_id}", box=box.SIMPLE)
        table.add_column("Score")
        table.add_column("Persona")
        table.add_row(
            str(data.get("score")), data.get("persona", {}).get("persona", "-")
        )
        console.print(table)
        console.print_json(data=data.get("factors", {}))

    def simulate_expense(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        amount = float(Prompt.ask("Expense amount", default="5000"))
        category = Prompt.ask("Category", default="general")
        payload = {
            "user_id": user_id,
            "expense_amount": amount,
            "category": category,
            "description": f"CLI simulation at {datetime.now(timezone.utc).isoformat()}",
        }
        result = self._request_backend("POST", "/api/simulate", json=payload)
        console.print_json(data=result)

    def trigger_transaction(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        amount = float(
            Prompt.ask("Amount (positive=credit, negative=debit)", default="-1200")
        )
        merchant = Prompt.ask("Merchant", default="CLI Merchant")
        category = Prompt.ask("Category", default="general")
        payload = {
            "user_id": user_id,
            "amount": amount,
            "merchant": merchant,
            "category": category,
        }
        result = self._request_backend(
            "POST", "/api/transactions/trigger", json=payload
        )
        console.print_json(data=result)

    def trigger_scenario(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        scenario = Prompt.ask(
            "Scenario", choices=list(SCENARIOS), default="large_medical_expense"
        )
        token = self._admin_token()
        payload = {"user_id": user_id, "scenario_type": scenario}
        result = self._request_proxy(
            "POST", "/admin/scenario", json=payload, token=token
        )
        console.print_json(data=result)

    def upsert_profile(self) -> None:
        user_id = Prompt.ask("User ID", default="user_010")
        balance = float(Prompt.ask("Current balance", default="25000"))
        available = float(Prompt.ask("Available balance", default=str(balance)))
        add_txn = Confirm.ask("Attach sample transactions?", default=False)
        transactions = None
        if add_txn:
            amount = float(Prompt.ask("Sample debit amount", default="-1500"))
            transactions = [
                {
                    "user_id": user_id,
                    "amount": amount,
                    "merchant": "CLI Setup",
                    "category": "dining",
                    "description": "Seeded via dashboard",
                }
            ]
        payload = {
            "user_id": user_id,
            "current_balance": balance,
            "available_balance": available,
            "transactions": transactions,
        }
        token = self._admin_token()
        result = self._request_proxy("POST", "/profiles", json=payload, token=token)
        console.print_json(data=result)

    def view_accounts(self) -> None:
        user_id = Prompt.ask("User ID", default="user_001")
        records = self._request_backend("GET", f"/api/accounts/{user_id}")
        if not records:
            console.print(f"[yellow]No accounts linked for {user_id}.[/yellow]")
            return
        table = Table(title=f"Accounts for {user_id}", box=box.SIMPLE)
        table.add_column("Type")
        table.add_column("Provider")
        table.add_column("Mask")
        table.add_column("Status")
        table.add_column("Current", justify="right")
        for acct in records:
            table.add_row(
                acct.get("account_type", "-"),
                acct.get("provider_id", "-"),
                acct.get("mask", "----"),
                acct.get("status", "-"),
                f"₹{acct.get('current_balance', 0):,.2f}",
            )
        console.print(table)

    def list_providers(self) -> None:
        records = self._request_backend("GET", "/api/providers/")
        if not records:
            console.print("[yellow]No providers configured.[/yellow]")
            return
        table = Table(title="Provider Catalog", box=box.SIMPLE)
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Channels")
        table.add_column("Latency", justify="right")
        for provider in records:
            table.add_row(
                provider.get("id", "-"),
                provider.get("name", "-"),
                provider.get("status", "-"),
                ", ".join(provider.get("channels", []) or []),
                f"{provider.get('latency_ms', 'n/a')}",
            )
        console.print(table)

    def watch_events(self) -> None:
        console.print("[cyan]Streaming events. Press Ctrl+C to stop.[/cyan]")
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "GET", f"{self.backend_url}/api/events/stream"
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line and line.startswith("data: "):
                            payload = line[6:]
                            console.print(f"[green]{payload}[/green]")
        except KeyboardInterrupt:
            console.print("\n[red]Stopped stream[/red]")

    def exit_app(self) -> None:
        console.print("Goodbye! 👋")
        sys.exit(0)

    def _request_backend(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        url = f"{self.backend_url}{path}"
        with httpx.Client(timeout=self.http_timeout) as client:
            resp = client.request(
                method, url, params=params, json=json, follow_redirects=True
            )
            resp.raise_for_status()
            return resp.json()

    def _request_proxy(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        token: str,
    ) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.proxy_url}{path}"
        with httpx.Client(timeout=self.http_timeout) as client:
            resp = client.request(
                method, url, params=params, json=json, headers=headers
            )
            resp.raise_for_status()
            return resp.json()

    def _user_token(self, user_id: str, role: str = "user") -> str:
        payload = {
            "user_id": user_id,
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    def _admin_token(self) -> str:
        return self._user_token("admin", role="admin")


SCENARIOS = {
    "large_medical_expense",
    "salary_drop",
    "subscription_spike",
}


def main() -> None:
    Dashboard().run()


if __name__ == "__main__":
    main()
