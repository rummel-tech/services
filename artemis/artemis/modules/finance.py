"""Finance management module for Artemis personal OS."""
from datetime import date
from typing import Any, Dict
from uuid import uuid4
from artemis.core.module import BaseModule, ModuleConfig, ModuleStatus, ModuleSummary, QuickAction


class FinanceModule(BaseModule):
    """Module for managing finances, budgets, and financial goals.
    
    Features:
    - Transaction tracking
    - Budget management
    - Financial goal setting
    - Investment tracking
    - Expense categorization
    """
    
    def __init__(self, config: ModuleConfig) -> None:
        """Initialize the finance module."""
        super().__init__(config)
        self.transactions: Dict[str, Any] = {}
        self.budgets: Dict[str, Any] = {}
        self.goals: Dict[str, Any] = {}
        self.investments: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize the finance module."""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the finance module."""
        self._initialized = False
    
    async def get_status(self) -> ModuleStatus:
        """Get the current status of the finance module."""
        return ModuleStatus(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            message=f"Tracking {len(self.transactions)} transactions and {len(self.budgets)} budgets"
        )
    
    async def handle_action(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle finance module actions."""
        if action == "add_transaction":
            transaction_id = data.get("id", f"transaction_{uuid4().hex[:8]}")
            self.transactions[transaction_id] = data
            return {"status": "success", "transaction_id": transaction_id}
        
        elif action == "create_budget":
            budget_id = data.get("id", f"budget_{uuid4().hex[:8]}")
            self.budgets[budget_id] = data
            return {"status": "success", "budget_id": budget_id}
        
        elif action == "set_goal":
            goal_id = data.get("id", f"goal_{uuid4().hex[:8]}")
            self.goals[goal_id] = data
            return {"status": "success", "goal_id": goal_id}
        
        elif action == "list_transactions":
            return {"transactions": list(self.transactions.values())}

        return {"status": "error", "message": f"Unknown action: {action}"}

    async def get_summary(self) -> ModuleSummary:
        """Get summary information for the finance module."""
        today = date.today()
        current_month = today.strftime("%Y-%m")

        monthly_spend = sum(
            float(t.get("amount", 0))
            for t in self.transactions.values()
            if t.get("date", "").startswith(current_month) and t.get("type") == "expense"
        )

        recent_transactions = sorted(
            self.transactions.values(),
            key=lambda x: x.get("date", ""),
            reverse=True
        )[:5]

        return ModuleSummary(
            name=self.name,
            enabled=self.is_enabled,
            healthy=self._initialized,
            stats={
                "transaction_count": len(self.transactions),
                "monthly_spend": monthly_spend,
                "budget_count": len(self.budgets),
            },
            recent_items=[{"type": "transaction", **t} for t in recent_transactions],
            quick_actions=[
                QuickAction(id="add_transaction", label="Add Transaction", action="add_transaction", icon="receipt_long"),
                QuickAction(id="create_budget", label="Create Budget", action="create_budget", icon="savings"),
            ],
        )
