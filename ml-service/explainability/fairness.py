import numpy as np
import pandas as pd
from bias_model.model_trainer import trainer_instance

def calculate_fairness_metrics() -> dict:
    df = trainer_instance.df
    if df is None or df.empty:
        df = trainer_instance.prepare_features_and_labels()
        
    model = trainer_instance.model
    if model is None:
        model = trainer_instance.train_model()
        
    X = df[trainer_instance.feature_names]
    predictions = model.predict(X)
    df["predicted_label"] = predictions
    
    # Group A = Privileged Proxy, Group B = Unprivileged Proxy
    group_a_mask = df["demographic_group_a"] == 1
    group_b_mask = df["demographic_group_a"] == 0
    
    # Selection Rates (Acceptance Rate)
    acc_rate_a = float(np.mean(df.loc[group_a_mask, "predicted_label"])) if int(group_a_mask.sum()) > 0 else 0.0
    acc_rate_b = float(np.mean(df.loc[group_b_mask, "predicted_label"])) if int(group_b_mask.sum()) > 0 else 0.0
    
    # Demographic Parity Difference: |P(Y^=1|A) - P(Y^=1|B)|
    dpd = abs(acc_rate_a - acc_rate_b)
    
    # Disparate Impact Ratio: Rate(Unprivileged) / Rate(Privileged)
    di_ratio = (acc_rate_b / acc_rate_a) if acc_rate_a > 0 else 1.0
    
    # 80% Rule check
    passes_80_rule = di_ratio >= 0.80
    
    interpretation = (
        f"The audited model accepts Group A (Privileged Proxy) at {round(acc_rate_a * 100, 1)}% "
        f"and Group B (Unprivileged Proxy) at {round(acc_rate_b * 100, 1)}%. "
        f"The Disparate Impact ratio is {round(di_ratio, 2)}. "
    )
    if not passes_80_rule:
        interpretation += "⚠️ WARNING: This model violates the 80% rule for equal opportunity hiring under EEOC guidelines."
    else:
        interpretation += "✅ PASSES: Disparate Impact is within the acceptable 80% threshold."
        
    return {
        "group_a_acceptance_rate": round(acc_rate_a, 3),
        "group_b_acceptance_rate": round(acc_rate_b, 3),
        "demographic_parity_difference": round(dpd, 3),
        "disparate_impact_ratio": round(di_ratio, 3),
        "passes_80_percent_rule": passes_80_rule,
        "sample_size_group_a": int(group_a_mask.sum()),
        "sample_size_group_b": int(group_b_mask.sum()),
        "interpretation": interpretation,
        "ground_truth_bias_disclosure": (
            "This audited screening model was intentionally trained on data containing controlled injected bias "
            "(Demographic proxy boost + Tier-1 college boost + severe employment gap penalties) "
            "to validate that the auditor correctly isolates algorithmic unfairness."
        )
    }

def calculate_mitigated_fairness_metrics() -> dict:
    df = trainer_instance.df
    if df is None or df.empty:
        df = trainer_instance.prepare_features_and_labels()
        
    mitigated_info = trainer_instance.train_mitigated_model()
    mit_model = mitigated_info["model"]
    
    X = df[trainer_instance.feature_names].copy()
    X["demographic_group_a"] = 0
    predictions = mit_model.predict(X)
    df_temp = df.copy()
    df_temp["mitigated_pred"] = predictions
    
    group_a_mask = df_temp["demographic_group_a"] == 1
    group_b_mask = df_temp["demographic_group_a"] == 0
    
    acc_a = float(np.mean(df_temp.loc[group_a_mask, "mitigated_pred"])) if int(group_a_mask.sum()) > 0 else 0.0
    acc_b = float(np.mean(df_temp.loc[group_b_mask, "mitigated_pred"])) if int(group_b_mask.sum()) > 0 else 0.0
    
    dpd = abs(acc_a - acc_b)
    di_ratio = (acc_b / acc_a) if acc_a > 0 else 1.0
    passes_80 = di_ratio >= 0.80
    
    return {
        "unmitigated": calculate_fairness_metrics(),
        "mitigated": {
            "group_a_acceptance_rate": round(acc_a, 3),
            "group_b_acceptance_rate": round(acc_b, 3),
            "demographic_parity_difference": round(dpd, 3),
            "disparate_impact_ratio": round(di_ratio, 3),
            "passes_80_percent_rule": passes_80,
            "interpretation": f"After reweighting sample distributions and removing proxy attributes, Disparate Impact improved to {round(di_ratio, 2)}."
        }
    }
