import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

# ------------------------------------------------------------
# Core calculator function
# ------------------------------------------------------------
def compute_retirement_projection(
    current_age,
    retirement_age,
    life_expectancy,

    # Starting balances
    traditional_ira_balance,
    roth_ira_balance,
    mutual_fund_balance,

    # Annual contributions (independent)
    annual_traditional_contribution,
    annual_roth_contribution,
    annual_mutual_contribution,

    # Returns + inflation
    return_before_retirement,   # percent
    return_after_retirement,    # percent
    inflation_rate,             # percent

    # Spending + additions (after retirement)
    annual_spending_goal,
    healthcare_annual_cost,          # dollars in today's terms (after retirement)
    vacation_travel_annual_amount,  # dollars in today's terms (after retirement)
    include_healthcare,              # boolean

    # Pension/SS
    monthly_pension,
    pension_start_age,
    include_pension,                # boolean

    monthly_social_security,
    social_security_start_age,
    include_social_security,       # boolean

    # Taxes
    tax_rate_traditional,  # percent
    tax_rate_mutual        # percent
):
    # Convert % inputs to decimals
    r_before = return_before_retirement / 100.0
    r_after = return_after_retirement / 100.0
    infl = inflation_rate / 100.0

    tax_trad = tax_rate_traditional / 100.0
    tax_mut = tax_rate_mutual / 100.0

    # Starting balances
    ira = float(traditional_ira_balance)
    roth = float(roth_ira_balance)
    mutual = float(mutual_fund_balance)

    ages = list(range(current_age, life_expectancy + 1))
    records = []

    projected_balance_at_retirement = None

    run_out_age = None
    funds_exhausted = False

    # Net factors after tax
    net_factor_trad = 1.0 - tax_trad
    net_factor_mut = 1.0 - tax_mut

    for age in ages:
        # If funds already exhausted, lock balances at 0
        if funds_exhausted:
            records.append({
                "Age": age,
                "Traditional IRA Balance": 0.0,
                "Roth IRA Balance": 0.0,
                "Mutual Fund Balance": 0.0,
                "Total Balance": 0.0,
                "Pension Income": 0.0,
                "Social Security Income": 0.0,
                "Spending Need": 0.0,
                "Shortfall": 0.0,
                "Traditional IRA Withdraw (Net)": 0.0,
                "Mutual Fund Withdraw (Net)": 0.0,
                "Roth Withdraw (Tax-Free)": 0.0,
                "Total Net Withdrawals": 0.0,
                "Total Portfolio Run Out?": "Yes"
            })
            continue

        # Defaults for this year
        pension_income = 0.0
        ss_income = 0.0
        spending_need = 0.0
        shortfall = 0.0

        ira_withdraw_net = 0.0
        mutual_withdraw_net = 0.0
        roth_withdraw = 0.0
        total_net_withdrawals = 0.0

        # BEFORE retirement: grow + add contributions
        if age < retirement_age:
            ira *= (1.0 + r_before)
            roth *= (1.0 + r_before)
            mutual *= (1.0 + r_before)

            # Add contributions to each account independently
            ira += annual_traditional_contribution
            roth += annual_roth_contribution
            mutual += annual_mutual_contribution

            # Capture end-of-year retirement balance
            if age == retirement_age - 1:
                projected_balance_at_retirement = ira + roth + mutual

            records.append({
                "Age": age,
                "Traditional IRA Balance": ira,
                "Roth IRA Balance": roth,
                "Mutual Fund Balance": mutual,
                "Total Balance": ira + roth + mutual,
                "Pension Income": 0.0,
                "Social Security Income": 0.0,
                "Spending Need": 0.0,
                "Shortfall": 0.0,
                "Traditional IRA Withdraw (Net)": 0.0,
                "Mutual Fund Withdraw (Net)": 0.0,
                "Roth Withdraw (Tax-Free)": 0.0,
                "Total Net Withdrawals": 0.0,
                "Total Portfolio Run Out?": "No"
            })
            continue

        # ON/AFTER retirement: grow balances with after-retirement return
        ira *= (1.0 + r_after)
        roth *= (1.0 + r_after)
        mutual *= (1.0 + r_after)

        # Pension/SS income toggles + start ages
        if include_pension and age >= pension_start_age:
            pension_income = monthly_pension * 12.0
        if include_social_security and age >= social_security_start_age:
            ss_income = monthly_social_security * 12.0

        years_since_retirement = age - retirement_age

        # Spending components inflate over time
        base_spending = annual_spending_goal * ((1.0 + infl) ** years_since_retirement)

        healthcare_part = 0.0
        if include_healthcare:
            healthcare_part = healthcare_annual_cost * ((1.0 + infl) ** years_since_retirement)

        vacation_part = vacation_travel_annual_amount * ((1.0 + infl) ** years_since_retirement)

        spending_need = base_spending + healthcare_part + vacation_part

        shortfall = max(0.0, spending_need - (pension_income + ss_income))

        # Withdraw in order: Traditional IRA → Mutual Funds → Roth
        ira_gross_withdraw = 0.0
        mutual_gross_withdraw = 0.0

        # ---- Traditional IRA (taxable) ----
        if shortfall > 0 and ira > 0:
            max_gross = ira
            if net_factor_trad > 0:
                gross_needed = shortfall / net_factor_trad
            else:
                gross_needed = max_gross  # if tax=100%, net factor is 0

            ira_gross_withdraw = min(max_gross, gross_needed)

            ira_tax = ira_gross_withdraw * tax_trad
            ira_withdraw_net = ira_gross_withdraw - ira_tax

            ira -= ira_gross_withdraw
            shortfall -= ira_withdraw_net
            total_net_withdrawals += ira_withdraw_net

        # ---- Mutual Funds (taxable) ----
        if shortfall > 0 and mutual > 0:
            max_gross = mutual
            if net_factor_mut > 0:
                gross_needed = shortfall / net_factor_mut
            else:
                gross_needed = max_gross

            mutual_gross_withdraw = min(max_gross, gross_needed)

            mutual_tax = mutual_gross_withdraw * tax_mut
            mutual_withdraw_net = mutual_gross_withdraw - mutual_tax

            mutual -= mutual_gross_withdraw
            shortfall -= mutual_withdraw_net
            total_net_withdrawals += mutual_withdraw_net

        # ---- Roth (tax-free) ----
        if shortfall > 0 and roth > 0:
            roth_withdraw = min(roth, shortfall)
            roth -= roth_withdraw
            shortfall -= roth_withdraw
            total_net_withdrawals += roth_withdraw

        total_balance = ira + roth + mutual

        if run_out_age is None and total_balance <= 1e-6:
            run_out_age = age
            funds_exhausted = True

        records.append({
            "Age": age,
            "Traditional IRA Balance": ira,
            "Roth IRA Balance": roth,
            "Mutual Fund Balance": mutual,
            "Total Balance": max(0.0, total_balance),
            "Pension Income": pension_income,
            "Social Security Income": ss_income,
            "Spending Need": spending_need,
            "Shortfall": max(0.0, shortfall),
            "Traditional IRA Withdraw (Net)": ira_withdraw_net,
            "Mutual Fund Withdraw (Net)": mutual_withdraw_net,
            "Roth Withdraw (Tax-Free)": roth_withdraw,
            "Total Net Withdrawals": total_net_withdrawals,
            "Total Portfolio Run Out?": "Yes" if funds_exhausted else "No"
        })

    df = pd.DataFrame(records)
    return df, projected_balance_at_retirement, run_out_age


# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title="Retirement Planner", layout="wide")
    st.title("🧓👵 Retirement Planner (Beginner-Friendly)")

    st.markdown("""
    This app projects retirement finances year-by-year using simplified assumptions:
    - Growth before retirement + contributions
    - After retirement: inflation-adjusted spending + pension/SS income
    - Withdrawals: Traditional IRA → Mutual Funds → Roth IRA
    - Simple flat tax model for Traditional + mutual withdrawals
    """)

    st.sidebar.header("📌 Inputs")

    # Ages
    current_age = st.sidebar.number_input("Current age", min_value=0, max_value=120, value=30, step=1)
    retirement_age = st.sidebar.number_input("Retirement age", min_value=0, max_value=120, value=65, step=1)
    life_expectancy = st.sidebar.number_input("Life expectancy", min_value=60, max_value=130, value=90, step=1)

    # Starting balances
    traditional_ira_balance = st.sidebar.number_input("Current Traditional IRA balance", min_value=0.0, value=50000.0, step=1000.0)
    roth_ira_balance = st.sidebar.number_input("Current Roth IRA balance", min_value=0.0, value=20000.0, step=1000.0)
    mutual_fund_balance = st.sidebar.number_input("Current mutual fund balance", min_value=0.0, value=15000.0, step=1000.0)

    # Contributions
    st.sidebar.subheader("💰 Annual contributions")
    annual_traditional_contribution = st.sidebar.number_input("Annual contribution to Traditional IRA", min_value=0.0, value=6000.0, step=500.0)
    annual_roth_contribution = st.sidebar.number_input("Annual contribution to Roth IRA", min_value=0.0, value=4000.0, step=500.0)
    annual_mutual_contribution = st.sidebar.number_input("Annual contribution to mutual funds", min_value=0.0, value=3000.0, step=500.0)

    # Returns + inflation
    return_before_retirement = st.sidebar.number_input("Return before retirement (%)", min_value=0.0, value=7.0, step=0.5)
    return_after_retirement = st.sidebar.number_input("Return after retirement (%)", min_value=0.0, value=4.0, step=0.5)
    inflation_rate = st.sidebar.number_input("Inflation rate (%)", min_value=0.0, value=2.5, step=0.1)

    # Spending
    st.sidebar.subheader("🧾 After-retirement spending")
    annual_spending_goal = st.sidebar.number_input(
        "Annual retirement spending goal (today's dollars)",
        min_value=0.0, value=45000.0, step=1000.0
    )

    include_healthcare = st.sidebar.toggle("Include healthcare expenses", value=True)
    healthcare_annual_cost = st.sidebar.number_input(
        "Annual healthcare cost (today's dollars)",
        min_value=0.0, value=6000.0, step=500.0,
        disabled=not include_healthcare
    )

    vacation_travel_annual_amount = st.sidebar.number_input(
        "Annual vacation/travel allocation (today's dollars)",
        min_value=0.0, value=3000.0, step=500.0
    )

    # Pension & Social Security toggles
    st.sidebar.subheader("🏦 Pension / Social Security")

    include_pension = st.sidebar.toggle("Include pension", value=True)
    monthly_pension = st.sidebar.number_input(
        "Monthly pension amount",
        min_value=0.0, value=0.0, step=100.0,
        disabled=not include_pension
    )
    pension_start_age = st.sidebar.number_input(
        "Pension start age",
        min_value=0, max_value=140, value=65, step=1,
        disabled=not include_pension
    )

    include_social_security = st.sidebar.toggle("Include Social Security", value=True)
    monthly_social_security = st.sidebar.number_input(
        "Monthly Social Security amount",
        min_value=0.0, value=0.0, step=100.0,
        disabled=not include_social_security
    )
    social_security_start_age = st.sidebar.number_input(
        "Social Security start age",
        min_value=0, max_value=140, value=67, step=1,
        disabled=not include_social_security
    )

    # Taxes
    st.sidebar.subheader("🧮 Taxes (simple model)")
    tax_rate_traditional = st.sidebar.number_input(
        "Tax rate for Traditional IRA withdrawals (%)",
        min_value=0.0, value=15.0, step=0.5
    )
    tax_rate_mutual = st.sidebar.number_input(
        "Tax rate for mutual fund withdrawals (%)",
        min_value=0.0, value=0.0, step=0.5
    )

    run = st.sidebar.button("▶️ Run Projection")

    # ------------------------------------------------------------
    # Run + Outputs
    # ------------------------------------------------------------
    if not run:
        st.info("Adjust inputs and click **Run Projection** to see results.")
        return

    if life_expectancy < current_age:
        st.error("Life expectancy must be >= current age.")
        return

    df, projected_balance_at_retirement, run_out_age = compute_retirement_projection(
        current_age=int(current_age),
        retirement_age=int(retirement_age),
        life_expectancy=int(life_expectancy),

        traditional_ira_balance=traditional_ira_balance,
        roth_ira_balance=roth_ira_balance,
        mutual_fund_balance=mutual_fund_balance,

        annual_traditional_contribution=annual_traditional_contribution,
        annual_roth_contribution=annual_roth_contribution,
        annual_mutual_contribution=annual_mutual_contribution,

        return_before_retirement=return_before_retirement,
        return_after_retirement=return_after_retirement,
        inflation_rate=inflation_rate,

        annual_spending_goal=annual_spending_goal,
        healthcare_annual_cost=healthcare_annual_cost,
        vacation_travel_annual_amount=vacation_travel_annual_amount,
        include_healthcare=include_healthcare,

        monthly_pension=monthly_pension,
        pension_start_age=int(pension_start_age),
        include_pension=include_pension,

        monthly_social_security=monthly_social_security,
        social_security_start_age=int(social_security_start_age),
        include_social_security=include_social_security,

        tax_rate_traditional=tax_rate_traditional,
        tax_rate_mutual=tax_rate_mutual
    )

    # ---------------- Summary ----------------
    st.subheader("📌 Summary")

    if projected_balance_at_retirement is not None:
        st.write(f"**Projected balance at retirement:** ${projected_balance_at_retirement:,.2f}")
    else:
        st.write("**Projected balance at retirement:** (N/A based on your input ages.)")

    if run_out_age is not None:
        st.write(f"**Estimated age when funds run out:** {run_out_age}")
    else:
        st.write("**Funds do not run out within life expectancy** (based on your inputs).")

    # ---------------- Total balance chart ----------------
    st.subheader("📈 Total portfolio balance over time")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["Age"], df["Total Balance"], marker="o", linewidth=2, color="tab:blue")
    ax.set_title("Total Portfolio Balance Over Time")
    ax.set_xlabel("Age")
    ax.set_ylabel("Total Balance ($)")
    ax.grid(True, linestyle="--", alpha=0.5)
    st.pyplot(fig)

    # ---------------- Breakdown charts for each account ----------------
    st.subheader("📊 Breakdown: each account balance over time")

    c1, c2 = st.columns(2)

    with c1:
        fig1, ax1 = plt.subplots(figsize=(6.5, 3.6))
        ax1.plot(df["Age"], df["Traditional IRA Balance"], marker="o", linewidth=2, color="tab:orange")
        ax1.set_title("Traditional IRA Balance")
        ax1.set_xlabel("Age")
        ax1.set_ylabel("Balance ($)")
        ax1.grid(True, linestyle="--", alpha=0.5)
        st.pyplot(fig1)

    with c2:
        fig2, ax2 = plt.subplots(figsize=(6.5, 3.6))
        ax2.plot(df["Age"], df["Roth IRA Balance"], marker="o", linewidth=2, color="tab:green")
        ax2.set_title("Roth IRA Balance")
        ax2.set_xlabel("Age")
        ax2.set_ylabel("Balance ($)")
        ax2.grid(True, linestyle="--", alpha=0.5)
        st.pyplot(fig2)

    # Mutual in full width
    fig3, ax3 = plt.subplots(figsize=(10, 3.8))
    ax3.plot(df["Age"], df["Mutual Fund Balance"], marker="o", linewidth=2, color="tab:purple")
    ax3.set_title("Mutual Fund Balance")
    ax3.set_xlabel("Age")
    ax3.set_ylabel("Balance ($)")
    ax3.grid(True, linestyle="--", alpha=0.5)
    st.pyplot(fig3)

    # ---------------- Main results table ----------------
    st.subheader("🧾 Annual results table")

    # Show a focused table first
    summary_cols = [
        "Age",
        "Total Balance",
        "Pension Income",
        "Social Security Income",
        "Spending Need",
        "Shortfall",
        "Traditional IRA Withdraw (Net)",
        "Mutual Fund Withdraw (Net)",
        "Roth Withdraw (Tax-Free)",
        "Total Net Withdrawals",
        "Total Portfolio Run Out?"
    ]
    st.dataframe(
        df[summary_cols].style.format({
            "Total Balance": "${:,.2f}",
            "Pension Income": "${:,.2f}",
            "Social Security Income": "${:,.2f}",
            "Spending Need": "${:,.2f}",
            "Shortfall": "${:,.2f}",
            "Traditional IRA Withdraw (Net)": "${:,.2f}",
            "Mutual Fund Withdraw (Net)": "${:,.2f}",
            "Roth Withdraw (Tax-Free)": "${:,.2f}",
            "Total Net Withdrawals": "${:,.2f}"
        }),
        use_container_width=True
    )

    # ---------------- Download CSV ----------------
    st.subheader("💾 Download results as CSV")

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download yearly results (CSV)",
        data=csv_bytes,
        file_name="retirement_projection_results.csv",
        mime="text/csv"
    )

    # ---------------- Optional full dataframe ----------------
    with st.expander("Show full dataset"):
        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()
