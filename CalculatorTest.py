import streamlit as st          #streamlit website interface
import pandas as pd
import numpy as np
import altair as alt

#TODO think about other dynamic drawdown options
#TODO set up GitHub account and publish on https://streamlit.io/cloud

#--- Load Account Based Pension Minimums ---#
APmin_array = pd.read_excel('ABP Minimums.xlsx',usecols=['APmin_ages','APmin_percentages'] )

#--- Load LifeTables ---#
LifeTable_array = pd.read_excel('ALT Male Life Tables.xlsx',usecols=['Age','lx','dx','px','qx','µx','ex','Lx','Tx'] )

#--- Load Age Pension Parameters ---#
header_rows = [0, 1]
AP_Parameters = pd.read_excel('Age Pension Parameters.xlsx',header=header_rows, index_col=0 )

#--- Load Return History ---#
Return_History = pd.read_excel('Return History.xlsx',index_col=0 )

#--- Age Pension Function ---#

def calculate_age_pension(bal, ann_inc, couple_status, homeowner_status, other_assets, ann_means, ap_age):
    """
    Calculates the annual age pension currently payable    
    """

    # --- 1. Set to current rate ---
    age_pension = AP_Parameters[(couple_status, homeowner_status)].loc['Full Age Pension (per fortnight)']

    # --- 2. calculate assets test reduction  ---
    if ap_age < 85:
        assets_test_assets = bal + 0.6 * ann_means + other_assets
    else:
        assets_test_assets = bal + 0.3 * ann_means + other_assets

    AT_lower_limit = AP_Parameters[(couple_status, homeowner_status)].loc['Asset Test Lower Limit']
    AT_reduction = AP_Parameters[(couple_status, homeowner_status)].loc['Asset Test Reduction (per fortnight)']

    assets_test_reduction = (assets_test_assets - AT_lower_limit) * AT_reduction / 1000 * 26

    # --- 3. calculate income  test reduction  ---

    IT_deeming_tier = AP_Parameters[(couple_status, homeowner_status)].loc['Deeming tier']
    IT_low_rate = AP_Parameters[(couple_status, homeowner_status)].loc['deeming rate 1']
    IT_high_rate = AP_Parameters[(couple_status, homeowner_status)].loc['deeming rate 2']
    IT_lower_limit = AP_Parameters[(couple_status, homeowner_status)].loc['Income Test Threshold (per fortnight)']
    IT_reduction = AP_Parameters[(couple_status, homeowner_status)].loc['Income Test Reduction']

    income_test_income = min(bal + other_assets,IT_deeming_tier)*IT_low_rate + max(bal + other_assets - IT_deeming_tier,0)*IT_high_rate + 0.6 * ann_inc

    income_test_reduction = (income_test_income - IT_lower_limit * 26) *IT_reduction

    # --- 4. annualise ---
    age_pension = max(age_pension * 26 - max(assets_test_reduction, income_test_reduction), 0)

    return age_pension


#--- Annuity Function ---#

def calculate_annuity_due(LT_series, ANstart_age, interest_rate, term_certain):
    """
    Calculates the value of a whole life annuity-due (a_x)
    using a given qx series, starting age, and interest rate.

    Formula: a_x = sum_{t=0 to omega-x} (v^t * t_p_x)

    where:
    - v = 1 / (1 + i)
    - t_p_x = probability of survival from age x to age x+t
    """

    # --- 1. Pre-computation ---
    v = 1.0 / (1.0 + interest_rate)
    ANmax_age = LT_series.index.max()  # Get the highest age in the table (e.g., 120)

    # --- 2. Calculate survival probabilities (t_p_x) ---
    # We will store t_p_x in a dictionary for easy lookup.
    # t_p_x = l_(x+t) / l_x
    # We can simplify by setting l_x = 1, so t_p_x = l_(x+t)

    t_p_x = {}
    current_p = 1.0  # This is 0_p_x (probability of surviving 0 years), which is 1
    t_p_x[0] = current_p

    annuity_value = 0.0

    # --- 3. Loop from t=0 up to the max age ---
    for t in range(0, (ANmax_age - start_age) + 1):
        ANcurrent_age = ANstart_age + t

        # Add the discounted value of the payment at time t
        # Payment is 1 if the person is alive (prob t_p_x)
        # Discount factor is v^t

        # t_p_x for t=0 was already set to 1.0
        if t > 0:
            # Calculate t_p_x = (t-1)_p_x * p_(x+t-1)
            # (t-1)_p_x is the previous `current_p`
            # p_(x+t-1) is (1 - q_(x+t-1))

            ANprev_age = ANcurrent_age - 1

            if ANprev_age not in LT_series.index:
                # If age is not in the table, assume survival prob is 0
                q = 1.0
            else:
                q = LT_series['qx'].loc[ANprev_age]

            p = 1.0 - q
            current_p = current_p * p  # This is the new t_p_x
            t_p_x[t] = current_p

        # Add the discounted value for this time step
        if t <= term_certain:
            discounted_value = (v ** t)
        else:
            discounted_value = (v ** t) * t_p_x[t]
        annuity_value += discounted_value

    return annuity_value


# --- Projection Function --- #

def calculate_projection(prj_balance, prj_growth_rate, exp_ret, prj_start_age, years, drawdown_option, dyn_opt, target_drawdown, annuity_pmnt, annuity_prch, AP_relationship, AP_homeowner, AP_otherassets, LT_series):
    """
    Calculates drawdown projection.
    """
    projection = []
    current_balance = prj_balance
    check_balance = prj_balance
    indexation = 1                              #indexation adjustment for smoothing experience

    for age in range(prj_start_age, 100 + 1):
        if drawdown_option == 'Minimum Withdrawal':
            drawdown = APmin_array['APmin_percentages'].loc[age] * current_balance
            age_pen = calculate_age_pension(current_balance, annuity_pmnt, AP_relationship, AP_homeowner, AP_otherassets, annuity_prch, age)
            total_pmnt = drawdown + age_pen + annuity_pmnt
            projection.append({'Age': age, 'Projected_Balance': current_balance, 'Drawdown': drawdown, 'Annuity_Payment': annuity_pmnt, 'Age_Pension': age_pen, 'Total_Payment' : total_pmnt, 'Real_Return': prj_growth_rate[age-prj_start_age+1]/100, 'Check_Balance': check_balance})
            check_balance = check_balance * (1 + prj_growth_rate[age-prj_start_age+1] / 100) - drawdown * (1 + prj_growth_rate[age-prj_start_age+1] / 200)
            current_balance = max(check_balance, 0)
        else:

            age_pen = calculate_age_pension(current_balance, annuity_pmnt, AP_relationship, AP_homeowner, AP_otherassets, annuity_prch, age)
            drawdown = min(
                max(target_drawdown * indexation,(APmin_array['APmin_percentages'].loc[age] * current_balance))-age_pen,
                current_balance * (1 + prj_growth_rate[age-prj_start_age+1] / 200)
            )
            total_pmnt = drawdown +age_pen + annuity_pmnt
            projection.append({'Age': age, 'Projected_Balance': current_balance, 'Drawdown': drawdown, 'Annuity_Payment': annuity_pmnt, 'Age_Pension': age_pen,  'Total_Payment' : total_pmnt, 'Real_Return': prj_growth_rate[age-prj_start_age+1]/100, 'Check_Balance': check_balance})
            # Smoothing calculations
            if dyn_opt == 'Smooth':
                # Adjust for actual vs expected account balance
                indexation = indexation * (1 + 1 *
                        ((check_balance * (1 + prj_growth_rate[age-prj_start_age+1] / 100) - drawdown * (1 + prj_growth_rate[age-prj_start_age+1] / 200)) /
                         (check_balance * (1 + exp_ret / 100) - drawdown * (1 + exp_ret / 200) ) - 1 ))
                # Adjust for extra year of age in longevity
                indexation = indexation * (1 - 1/LT_series['ex'].loc[age])

            else:
                indexation = indexation

            check_balance = check_balance * (1 + prj_growth_rate[age-prj_start_age+1] / 100) - drawdown * (1 + prj_growth_rate[age-prj_start_age+1] / 200)
            current_balance = max(check_balance,0)

    return pd.DataFrame(projection)


# --- Streamlit App ---

# Set the title of the app
st.title('Retirement Income Calculator')

# --- Sidebar for User Inputs ---
st.sidebar.header('Your Inputs')

balance = st.sidebar.number_input(
    'Super Balance ($)',
    min_value=0.0,
    max_value=2000000.0,
    value=500000.0,
    step=1000.0
)

growth_return = st.sidebar.slider(
    'Expected Growth Assets Real Returns (%)',
    min_value=0.0,
    max_value=10.0,
    value=5.0,
    step=0.1
)

defensive_return = st.sidebar.slider(
    'Expected Defensive Assets Real Returns (%)',
    min_value=0.0,
    max_value=10.0,
    value=2.0,
    step=0.1
)

years = np.arange(1970, 2025 + 1)
year_list_int = years.tolist()

start_year = st.sidebar.selectbox(
    'Pick a year to use historic returns or leave as 2025 for assumptions',
    options=year_list_int,
    index=55
)

growth_allocation = st.sidebar.slider(
    'Growth_Allocation (%)',
    min_value=0,
    max_value=100,
    value=70
)

annuity_allocation = st.sidebar.slider(
    'Annuity_Allocation (%)',
    min_value=0,
    max_value=(100-growth_allocation),
    value=0
)

start_age = st.sidebar.slider(
    'Starting Age',
    min_value=65,
    max_value=75,
    value=65
)

max_age = st.sidebar.slider(
    'Maximum Age',
    min_value=80,
    max_value=100,
    value=94
)

drawdown_option = st.sidebar.selectbox(
    'Starting Drawdown Option',
    ('Minimum Withdrawal','Level Real Income')
)

dynamic_option = st.sidebar.selectbox(
    'Dynamic Adjustment for Experience',
    ('None','Smooth')                       #Full adjustment for experience removed (in drawdown with minimums)
)

AgePension_Relationship = st.sidebar.selectbox(
    'Relationship Status for Age Pension',
    ('Single','Couple')
)

AgePension_Homeowner = st.sidebar.selectbox(
    'Homeowner Status for Age Pension',
    ('Homeowner','Non-Homeowner')
)

AgePension_Other_Assets = st.sidebar.number_input(
    "Other Assets for Age Pension (Including Spouse's Assets)",
    min_value=0.0,
    max_value=10000000.0,
    value=0.0,
    step=1000.0
)



# --- Main Webpage for Outputs ---

st.header('Projection Results')

# Calculations
# Set Parameters
growth_rate = growth_return * growth_allocation/100 + defensive_return * (1 - growth_allocation/100)
years = max_age - start_age
returns = np.arange(1, 36)
returns = np.full(37, growth_rate)

# Annuity calculations
Annuity_Val = calculate_annuity_due(LifeTable_array, start_age, defensive_return/100, 0)
Annuity_Purchase = annuity_allocation / 100 * balance
Annuity_Income = Annuity_Purchase / Annuity_Val
balance = balance - annuity_allocation / 100 * balance

# Run Projection
if st.sidebar.button('Run Projection'):
    # Get level income amount
    if drawdown_option == 'Level Real Income':
        target_drawdown = balance / years
        iteration = 0
        projection_df = calculate_projection(balance, returns, growth_rate, start_age, years, drawdown_option, "None", target_drawdown,
                                             Annuity_Income, Annuity_Purchase,
                                             AgePension_Relationship, AgePension_Homeowner, AgePension_Other_Assets, LifeTable_array)
        while abs(projection_df.iloc[years, 1]) > target_drawdown / 1000 and iteration < 50:
            target_drawdown = target_drawdown + (
                        projection_df.iloc[years, 1] / years) / 2  # look at remaining balance and respread
            iteration = iteration + 1
            projection_df = calculate_projection(balance, returns, growth_rate, start_age, years, drawdown_option, "None",
                                                 target_drawdown, Annuity_Income, Annuity_Purchase,
                                                 AgePension_Relationship, AgePension_Homeowner, AgePension_Other_Assets, LifeTable_array)
    else:
        target_drawdown = 0

    #get actual returns
    if start_year < 2025:
        final_year = min(2024,start_year  + 36)             #Final year is up to 36 years after start or 2024 (end of data)
        end_index = final_year - start_year + 1             #number of years of returns is inclusive of end and start

        historical_slice = Return_History.loc[start_year:final_year,['Real Growth Return', 'Real Defensive Return']]

        returns_subset = (
            historical_slice['Real Growth Return'] * growth_allocation +
            historical_slice['Real Defensive Return'] * (1 - growth_allocation)
        ).values
        returns[1:end_index] = returns_subset[0:end_index-1]        #0 is the first year of subset is the selected start, projection yses year + 1

    # Run actual projection with actual returns (and level income if selected)
    projection_df = calculate_projection(balance, returns,  growth_rate, start_age, years, drawdown_option, dynamic_option, target_drawdown,
                                         Annuity_Income, Annuity_Purchase,
                                         AgePension_Relationship, AgePension_Homeowner, AgePension_Other_Assets, LifeTable_array)


    st.subheader(f'Projection targeting income until {max_age}:')

# Display the data
    columns_to_show = ['Age', 'Projected_Balance', 'Drawdown', 'Annuity_Payment', 'Age_Pension', 'Total_Payment', 'Real_Return'] # add 'Check_Balance' to display in testing
    df_subset = projection_df[columns_to_show]
    st.dataframe(df_subset.style.format({'Projected_Balance': '${:,.2f}', 'Drawdown': '${:,.2f}', 'Annuity_Payment': '${:,.2f}', 'Age_Pension': '${:,.2f}' , 'Total_Payment': '${:,.2f}', 'Real_Return': '{:.1%}'}))

# Display a chart
    st.subheader('Projection Chart')

# --- 1. RESHAPE DATA FOR STACKING ---
# We melt the DataFrame to stack 'Drawdown' and 'Annuity_Payment'
# into one column ('Value') using 'Age' as the identifier.
    measure_order = {
        'Age_Pension': 1,
        'Annuity_Payment': 2,
        'Drawdown': 3
    }

    df_melted = projection_df.melt(
        id_vars=['Age', 'Projected_Balance'],  # Keep these columns as identifiers
        value_vars=['Age_Pension', 'Annuity_Payment', 'Drawdown'],  # The columns we want to stack
        var_name='Measure_Type',  # New column to hold the names ('Drawdown', 'Annuity_Payment')
        value_name='Value'  # New column to hold the amounts
    )

# Add the new sort order column using a pandas map
    df_melted['Stack_Order'] = df_melted['Measure_Type'].map(measure_order)

# Defined the Base, using the melted data for the bars
    base = alt.Chart(df_melted).encode(
        x=alt.X('Age', title='Age')
    )

# 3. Create the STACKED Bar Chart (Primary Y-axis: Drawdown + Annuity_Payment)
    bar_chart = base.mark_bar().encode(
        # Y-axis now uses the combined 'Value' column
        y=alt.Y('Value', axis=alt.Axis(title='Annual Amounts (Stacked Bars)', titleColor='#4CAF50'), scale=alt.Scale(zero=True)),

        # The key to stacking: use the Measure_Type for color, which Altair recognizes as a stack group
        color=alt.Color('Measure_Type', title='Payment Type'),

        # Use the Stack_Order column to control the stacking order
        # It must be a quantitative field (':Q')
        order=alt.Order('Stack_Order:Q', sort='ascending'),

        # Tooltip to show all three values upon hover
        tooltip=[
            alt.Tooltip('Age'),
            alt.Tooltip('Measure_Type', title='Type'),
            alt.Tooltip('Value', title='Amount', format='$,.0f')
        ]
    ).properties(title="Balance and Annual Amounts by Age")

# 4. Create the Line Chart (Secondary Y-axis: Balance)
# IMPORTANT: The line chart must still reference the ORIGINAL projection_df
# because df_melted does not contain a single 'Projected_Balance' column per Age.
    line_chart_base = alt.Chart(projection_df).encode(
        x=alt.X('Age', title='Age')
    )

    line_chart = line_chart_base.mark_line(point=True).encode(
        # Y-axis for Balance - set scale to 'independent' for dual axis
        y=alt.Y('Projected_Balance', axis=alt.Axis(title='Balance (Line)', titleColor='#2196F3'), scale=alt.Scale(zero=True)),
        color=alt.value('#2196F3'),  # Line color
        tooltip=[
            alt.Tooltip('Age'),
            alt.Tooltip('Projected_Balance', title='Balance', format='$,.0f')
        ]
    )

# 5. Combine (Layer) the Charts and Configure Secondary Axis
# The resolve_scale is crucial for creating the dual-axis effect
    mixed_chart = alt.layer(bar_chart, line_chart).resolve_scale(
        y='independent'  # Makes the two Y-axes independent
    ).interactive()  # Optional: adds zooming and panning

# 6. Display the Chart in Streamlit
    st.altair_chart(mixed_chart, use_container_width=True)

# Disclaimer
    st.info('No liability is accepted for use of this calculator. This calculator has been developed for experimental purposes only. All results should be separately verified.')

# test data

#    st.dataframe(Return_History)
#    st.dataframe(returns_subset)

else:
    st.info('Adjust the inputs in the sidebar and click "Run Projection".')
    st.info('No liability is accepted for use of this calculator. This calculator has been developed for experimental purposes only. All results should be separately verified.')
