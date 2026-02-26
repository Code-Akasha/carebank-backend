def calculate_surplus(income: float, expenses: float) -> float:
    return max(0.0, income - expenses)

def forecast_impact(current_balance: float, scheduled_expenses: float, simulated_expense: float) -> float:
    """
    Calculates the end of month balance if a simulated expense is incurred.
    This guarantees accuracy for the What-If Simulator feature.
    """
    return current_balance - scheduled_expenses - simulated_expense

def check_eligibility(user_profile: dict, product_rules: dict) -> bool:
    """
    Checks if a user is eligible for a product based on deterministic rules.
    Example:
    user_profile = {"credit_score": 750, "balance": 5000}
    product_rules = {"min_credit_score": 700, "min_balance": 1000}
    """
    for rule_key, required_value in product_rules.items():
        # Map product rule keys to user profile keys if necessary, or assume direct match
        user_key = rule_key.replace("min_", "").replace("max_", "")
        user_val = user_profile.get(user_key)
        
        if user_val is None:
            return False
        
        if rule_key.startswith("min_"):
            if user_val < required_value:
                return False
        elif rule_key.startswith("max_"):
            if user_val > required_value:
                return False
        elif user_val != required_value:
            return False
            
    return True
