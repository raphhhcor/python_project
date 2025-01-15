from pybacktestchain.broker import StopLoss
from pybacktestchain.blockchain import load_blockchain
import streamlit as st
import pandas as pd
from datetime import datetime
import utils
import plotly.express as px
import plotly.graph_objects as go

# Set verbosity for logging
verbose = False  # Set to True to enable logging, or False to suppress it

# Configure the page
st.set_page_config(page_title="Backtest Interface", layout="wide")

# Page title
st.title("Backtest Interface")

# Section 1: User inputs
st.header("Configure Backtest Parameters")
with st.container(border=True):
    # General inputs
    with st.expander("General Parameters", True):
        initial_date = st.date_input("Start Date", value=datetime(2019, 1, 1))
        final_date = st.date_input("End Date", value=datetime(2020, 1, 1))
        file_name = st.text_input("Backtest File Name", placeholder="Leave empty for default name")
        file_name = None if file_name == "" else file_name
        initial_cash = st.number_input("Initial Cash ($)", value=1000000, step=1000)

    # Strategy inputs
    with st.expander("Strategy Parameters"):
        gamma = st.number_input("Risk Parameter (gamma)", min_value=0.0, value=1.0, step=0.1)
        bounds = st.text_input("Bounds", value="[(0.0, 1.0)]")
        cons = st.text_input(
            "Constraints (cons)",
            value="{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}"
        )
        # Default stock universe
        default_universe = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", 
            "TSLA", "NVDA", "INTC", "CSCO", "NFLX"
        ]
        
        # Multiselect for predefined stock universe
        selected_universe = st.multiselect(
            "Select Stocks for Universe",
            options=default_universe,
            default=default_universe
        )
        
        # Input to add a custom stock to the universe
        new_stock = st.text_input("Add a Custom Stock to the Universe")
        
        if new_stock and new_stock not in selected_universe:
            selected_universe.append(new_stock)
            st.success(f"Stock '{new_stock}' has been added to the universe.")
        elif new_stock in selected_universe:
            st.warning(f"Stock '{new_stock}' is already in the universe.")
        else:
            st.warning("Please enter a valid stock if you want to add it.")

        # Display the final selected universe
        st.write("Current Stock Universe:", selected_universe)

    # Rebalancing and risk model options
    with st.expander("Advanced Options"):
        rebalance_flag = st.selectbox("Rebalancing", options=["EndOfMonth"], index=0)
        risk_model = st.selectbox("Risk Model", options=["StopLoss"], index=0)

    # Button to submit inputs
    submitted = st.button(label="Run Backtest")

# Section 2: Results
if submitted:
    st.header("Backtest Results")
    
    # Create a CustomFirstTwoMoments instance with the gamma parameter
    custom_moments = utils.CustomFirstTwoMoments(gamma=gamma)
    
    # Create a CustomBacktest instance
    backtest = utils.CustomBacktest(
        initial_date=datetime.combine(initial_date, datetime.min.time()),
        final_date=datetime.combine(final_date, datetime.min.time()),
        information_class=utils.CustomFirstTwoMoments,
        risk_model=StopLoss,
        name_blockchain='backtest',
        verbose=verbose,
        backtest_name=file_name,
    )
    
    # Run the backtest
    backtest.run_backtest()
    block_chain = load_blockchain('backtest')
    # Check if the blockchain is valid
    df_portfolio_mvmt = df = backtest.broker.get_transaction_log()
    # Convertir la colonne Date en format datetime pour le tri et les graphiques
    df_portfolio_mvmt['Date'] = pd.to_datetime(df_portfolio_mvmt['Date'])

    # Display results (placeholder example)
    st.write(f"Backtest '{backtest.backtest_name}' completed successfully!")

    # Expanders for results
    with st.expander("Processed Results (Key Metrics and Analysis)", expanded=True):
        summary = df_portfolio_mvmt.groupby('Ticker').agg(
            Total_Buy=('Quantity', lambda x: sum(x[df_portfolio_mvmt.loc[x.index, 'Action'] == 'BUY'])),
            Total_Sell=('Quantity', lambda x: sum(x[df_portfolio_mvmt.loc[x.index, 'Action'] == 'SELL'])),
            Net_Quantity=('Quantity', lambda x: sum(x[df_portfolio_mvmt.loc[x.index, 'Action'] == 'BUY']) - sum(x[df_portfolio_mvmt.loc[x.index, 'Action'] == 'SELL'])),
            Total_Investment=('Price', lambda x: sum(x[df_portfolio_mvmt.loc[x.index, 'Action'] == 'BUY'] * df_portfolio_mvmt.loc[x.index, 'Quantity'][df_portfolio_mvmt.loc[x.index, 'Action'] == 'BUY']))
        ).reset_index()
        st.title("Summary of Transactions by Ticker")
        st.dataframe(summary)


        # Garder uniquement la dernière ligne pour chaque date
        df_portfolio_mvmt = df_portfolio_mvmt.sort_values(by=['Date']).groupby('Date').last().reset_index()

        # Création du graphique avec points reliés par une ligne
        st.title("Evolution of Cash Over Time")
        fig = go.Figure()

        # Ajouter les points et les lignes
        fig.add_trace(go.Scatter(
            x=df_portfolio_mvmt['Date'],
            y=df_portfolio_mvmt['Cash'],
            mode='lines+markers',
            name='Cash',
            line=dict(color='blue'),
            marker=dict(size=8)
        ))

        # Personnalisation du graphique
        fig.update_layout(
            title="Evolution of Cash Over Time",
            xaxis_title="Date",
            yaxis_title="Cash ($)",
            template="plotly_white",
            hovermode="x unified"
        )
        # Afficher le graphique dans Streamlit
        st.plotly_chart(fig)


    ## Display the Blockchain results
    with st.expander("Blockchain Monitoring (Raw Data)", expanded=False):
        st.subheader("Blockchain Data")
        if block_chain.is_valid():
            st.write("The blockchain is valid.")
        else:
            st.write("The blockchain is not valid.")
        st.write("Below is the raw blockchain data:")
        for i in utils.split_text_by_lines(str(block_chain)):
            st.markdown(
                f"<div style='font-size:12px; font-family:monospace;'>{i}</div>",
                unsafe_allow_html=True
            )
        st.write(f"Blockchain Valid: {block_chain.is_valid()}")

    with st.expander("Portfolio Movements (Raw Data)", expanded=False):
        st.subheader("Portfolio Transactions")
        # Placeholder for raw portfolio movement data (replace with actual data)
        st.dataframe(df_portfolio_mvmt)

# Footer or additional spacing
st.write("---")
st.caption("Streamlit Interface for Backtest Management.")
