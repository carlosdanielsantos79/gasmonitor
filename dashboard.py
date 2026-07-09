import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="EU Oil Bulletin Dashboard", layout="wide")

# --- DATA LOADING (ONLINE OR LOCAL) ---
URL = "https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx"

@st.cache_data(ttl=86400) # Cache data for 24 hours to ensure speed
def load_data(url):
    try:
        # Load both sheets directly from the web URL
        df_with = pd.read_excel(url, sheet_name="Prices with taxes", header=0)
        df_wo = pd.read_excel(url, sheet_name="Prices wo taxes", header=0)
        return df_with, df_wo
    except Exception as e:
        st.error(f"Failed to fetch live data from EC website: {e}")
        st.info("Attempting to load local fallback files...")
        # Local fallback if you run locally with your uploaded CSV files
        try:
            df_with = pd.read_csv("Weekly_Oil_Bulletin_Prices_History_maticni_4web (2).xlsx - Prices with taxes.csv")
            df_wo = pd.read_csv("Weekly_Oil_Bulletin_Prices_History_maticni_4web (2).xlsx - Prices wo taxes.csv")
            return df_with, df_wo
        except Exception as local_e:
            st.error(f"Local files could not be read: {local_e}")
            return None, None

st.title("🇪🇺 Weekly Oil Bulletin Price Analytics Dashboard")
st.markdown("This dashboard monitors and benchmarks fuel developments across the EU from 2005 onwards.")
st.markdown("<small>Data source: Weekly Oil Bulletin Price Developments (https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en).</small>", unsafe_allow_headers=False, unsafe_allow_html=True)


df_with, df_wo = load_data(URL)

if df_with is not None and df_wo is not None:
    # --- SIDEBAR CONTROLS ---
    st.sidebar.header("Dashboard Configuration")
    
    # 1. Tax Treatment Select
    tax_option = st.sidebar.selectbox("Select Tax Mode", ["Without Taxes", "With Taxes"])
    df_selected = df_wo if tax_option == "Without Taxes" else df_with
    
    # Standardize first column name to 'Date'
    df_selected.rename(columns={df_selected.columns[0]: 'Date'}, inplace=True)
    df_selected['Date'] = pd.to_datetime(df_selected['Date'], errors='coerce')
    df_selected = df_selected.dropna(subset=['Date']).sort_values('Date')
    
    # Clean column mapping definitions
    suffix = "wo_tax" if tax_option == "Without Taxes" else "with_tax"
    
    product_mapping = {
        "Euro-super 95": "euro95",
        "Gas oil automotive (Diesel)": "diesel",
        "GPL (LPG)": "LPG"
    }
    
    # 2. Product Selector
    selected_prod_label = st.sidebar.selectbox("Fuel Type", list(product_mapping.keys()))
    prod_key = product_mapping[selected_prod_label]
    
    # Extract available country codes automatically from headers
    all_cols = df_selected.columns
    countries = sorted(list(set([c.split('_')[0] for c in all_cols if f"_{suffix}_" in c or f"_price_" in c])))
    
    # Set default indices for intuitive load (e.g., PT vs. EUR if available)
    default_target_idx = countries.index("PT") if "PT" in countries else 0
    default_base_idx = countries.index("EUR") if "EUR" in countries else 0

    # 3. Dynamic Country Country Selections
    target_country = st.sidebar.selectbox("Primary Analysis Country", countries, index=default_target_idx)
    baseline_country = st.sidebar.selectbox("Reference Benchmark Country", countries, index=default_base_idx)
    
    # 4. Date Range Filter
    min_date = df_selected['Date'].min().to_pydatetime()
    max_date = df_selected['Date'].max().to_pydatetime()
    start_date, end_date = st.sidebar.slider("Select Period", min_value=min_date, max_value=max_date, value=(min_date, max_date))
    
    # Filter dataset
    mask = (df_selected['Date'] >= pd.to_datetime(start_date)) & (df_selected['Date'] <= pd.to_datetime(end_date))
    df_filtered = df_selected.loc[mask].copy()
    
    # Resolve exact column headers dynamically
    target_col = f"{target_country}_price_{suffix}_{prod_key}"
    base_col = f"{baseline_country}_price_{suffix}_{prod_key}"
    
    # Fallback to loose matches if exact headers shift
    if target_col not in df_filtered.columns:
        target_col = [c for c in df_filtered.columns if f"{target_country}_" in c and prod_key in c][0]
    if base_col not in df_filtered.columns:
        base_col = [c for c in df_filtered.columns if f"{baseline_country}_" in c and prod_key in c][0]
        
    # Convert prices to 'per liter' by dividing by 1000
    df_filtered['Target_Per_Liter'] = pd.to_numeric(df_filtered[target_col], errors='coerce') / 1000.0
    df_filtered['Base_Per_Liter'] = pd.to_numeric(df_filtered[base_col], errors='coerce') / 1000.0
    
    # Calculate Dynamic Ratio (Target / Baseline)
    df_filtered['Price_Ratio'] = df_filtered['Target_Per_Liter'] / df_filtered['Base_Per_Liter']
    
    # Drop rows without valid numerical content for charting
    df_plot = df_filtered.dropna(subset=['Target_Per_Liter', 'Base_Per_Liter'])

    # --- METRICS DISPLAYS ---
    col1, col2, col3 = st.columns(3)
    latest_row = df_plot.iloc[-1] if not df_plot.empty else None
    
    if latest_row is not None:
        col1.metric(f"Latest {target_country} Price", f"€{latest_row['Target_Per_Liter']:.3f} /L")
        col2.metric(f"Latest {baseline_country} Benchmark", f"€{latest_row['Base_Per_Liter']:.3f} /L")
        col3.metric(f"Price Ratio ({target_country} / {baseline_country})", f"{latest_row['Price_Ratio']:.2%}")
    
    # --- CHART GENERATION (PLOTLY) ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Target Country Absolute Price Line
    fig.add_trace(
        go.Scatter(x=df_plot['Date'], y=df_plot['Target_Per_Liter'], name=f"{target_country} Price", line=dict(color='#FF4B4B', width=2)),
        secondary_y=False,
    )
    
    # Benchmark Country Absolute Price Line
    fig.add_trace(
        go.Scatter(x=df_plot['Date'], y=df_plot['Base_Per_Liter'], name=f"{baseline_country} Benchmark Price", line=dict(color='#0068C9', width=2)),
        secondary_y=False,
    )
    
    # Dynamic Ratio Line
    fig.add_trace(
        go.Scatter(x=df_plot['Date'], y=df_plot['Price_Ratio'], name=f"Ratio ({target_country} / {baseline_country})", line=dict(color='#29B5E8', width=1.5, dash='dot')),
        secondary_y=True,
    )
    
    # Formatting layout
    fig.update_layout(
        title=f"Time-Series: {selected_prod_label} Fuel Price Comparison ({tax_option})",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20)
    )
    
    fig.update_yaxes(title_text="Price (€ per Liter)", secondary_y=False)
    fig.update_yaxes(title_text="Ratio Factor (1.0 = Parity)", tickformat=".2f", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # --- RAW DATA TABLE ---
    with st.expander("View Filtered Data Table"):
        st.dataframe(df_plot[['Date', target_col, base_col, 'Target_Per_Liter', 'Base_Per_Liter', 'Price_Ratio']].rename(
            columns={target_col: f"{target_country} Raw (per 1k L)", base_col: f"{baseline_country} Raw (per 1k L)"}
        ))
else:
    st.warning("Please verify data source connection.")
