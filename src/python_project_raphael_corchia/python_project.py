import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pybacktestchain.blockchain import load_blockchain
from pybacktestchain.broker import Backtest, Broker, EndOfMonth, StopLoss
from pybacktestchain.data_module import FirstTwoMoments
from scipy.optimize import minimize

## Define a custom class of the first two moments one in order to be able to modify some parameters ##
@dataclass
class CustomFirstTwoMoments(FirstTwoMoments):
    gamma: float = 1.0  # Default risk aversion parameter
    cons: list = None  # Default to None, will define later if not provided
    bounds: list = None  # Default to None, will define later if not provided

    def __post_init__(self):
        if self.cons is None:
            # Default constraint: portfolio weights sum to 1
            self.cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1}]
        if self.bounds is None:
            # Default bounds: allow short selling
            self.bounds = [(0.0, 1.0)]  # Change if needed

    def compute_portfolio(self, t: datetime, information_set):
        try:
            mu = information_set["expected_return"]
            Sigma = information_set["covariance_matrix"]
            n = len(mu)

            # Objective function
            obj = lambda x: -x.dot(mu) + self.gamma / 2 * x.dot(Sigma).dot(x)  # noqa: E731

            # Initial guess: equal weights
            x0 = np.ones(n) / n

            # Minimize
            res = minimize(obj, x0, constraints=self.cons, bounds=self.bounds)

            # Prepare dictionary
            portfolio = {k: None for k in information_set["companies"]}

            # If optimization converged, update portfolio
            if res.success:
                for i, company in enumerate(information_set["companies"]):
                    portfolio[company] = res.x[i]
            else:
                raise Exception("Optimization did not converge")

            return portfolio
        except Exception as e:
            # If something goes wrong, return an equal weight portfolio but warn the user
            logging.warning(
                "Error computing portfolio, returning equal weight portfolio"
            )
            logging.warning(e)
            return {
                k: 1 / len(information_set["companies"])
                for k in information_set["companies"]
            }


## Define a custom class of the backtest one in order to be able to modify some parameters ##
class CustomBacktest(Backtest):
    def __init__(
        self,
        *args,
        backtest_name: str = None,
        initial_cash: float = 1_000_000,
        **kwargs,
    ):
        self.initial_cash = initial_cash
        self.broker = Broker(cash=self.initial_cash, verbose=self.verbose)
        super().__init__(*args, **kwargs)
        # if backtest_name is None, use teh default value of the Backtest class
        self.backtest_name = (
            backtest_name if backtest_name is not None else self.backtest_name
        )


def split_text_by_lines(text):
    # Split the text into lines
    lines = text.splitlines()
    # Remove empty lines and strip whitespace
    return [line.strip() for line in lines if line.strip()]


def main():
    # Set verbosity for logging
    verbose = False  # Set to True to enable logging, or False to suppress it

    # Configure the page
    st.set_page_config(page_title="Backtest Interface", layout="wide")

    # Page title
    st.title("Backtest Interface")

    ###################### Section 1: User inputs ######################
    st.header("Configure Backtest Parameters")
    with st.container(border=True):
        ######## General inputs ########
        with st.expander("General Parameters", True):
            initial_date = st.date_input("Start Date", value=datetime(2019, 1, 1))
            final_date = st.date_input("End Date", value=datetime(2020, 1, 1))
            file_name = st.text_input(
                "Backtest File Name", placeholder="Leave empty for default name"
            )
            file_name = None if file_name == "" else file_name
            initial_cash = st.number_input("Initial Cash ($)", value=1000000, step=1000)

        ######## Strategy inputs ########
        with st.expander("Strategy Parameters"):
            st.number_input(
                "Risk Parameter (gamma)",
                min_value=0.0,
                value=1.0,
                step=0.1,
                disabled=True,
            )
            st.text_input("Bounds", value="[(0.0, 1.0)]", disabled=True)
            st.text_input(
                "Constraints (cons)",
                value="{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}",
                disabled=True,
            )
            # Default stock universe
            default_universe = [
                "AAPL",
                "MSFT",
                "GOOGL",
                "AMZN",
                "META",
                "TSLA",
                "NVDA",
                "INTC",
                "CSCO",
                "NFLX",
            ]

            # Display the final selected universe
            st.write("Current Stock Universe:", default_universe)

        ######## Rebalancing and risk model options ########
        with st.expander("Advanced Options"):
            rebalance_flag = st.selectbox(
                "Rebalancing", options=["EndOfMonth"], index=0
            )
            rebalance_flag = EndOfMonth if rebalance_flag == "EndOfMonth" else None
            risk_model = st.selectbox("Risk Model", options=["StopLoss"], index=0)
            risk_model = StopLoss if risk_model == "StopLoss" else None

        # Button to submit inputs
        submitted = st.button(label="Run Backtest")

    st.markdown("---")

    ###################### Section 2: Results ######################
    if submitted:
        st.header("Backtest Results")

        # Create a CustomBacktest instance
        backtest = CustomBacktest(
            initial_date=datetime.combine(initial_date, datetime.min.time()),
            final_date=datetime.combine(final_date, datetime.min.time()),
            information_class=CustomFirstTwoMoments,
            risk_model=StopLoss,
            name_blockchain="backtest",
            verbose=verbose,
            backtest_name=file_name,
            initial_cash=initial_cash,
        )

        # Run the backtest
        backtest.run_backtest()
        block_chain = load_blockchain("backtest")
        df_portfolio_mvmt = backtest.broker.get_transaction_log()

        # Convert Date column to datetime for sorting and plotting
        df_portfolio_mvmt["Date"] = pd.to_datetime(df_portfolio_mvmt["Date"])

        # Display results
        st.write(f"Backtest '{backtest.backtest_name}' completed successfully!")

        # Expanders for results
        with st.expander("Processed Results (Key Metrics and Analysis)", expanded=True):
            ###################### Summary of Transactions by Ticker ######################
            with st.container(border=True):
                cols = st.columns(2)
                with cols[0]:
                    summary = (
                        df_portfolio_mvmt.groupby("Ticker")
                        .agg(
                            Total_Buy=(
                                "Quantity",
                                lambda x: sum(
                                    x[df_portfolio_mvmt.loc[x.index, "Action"] == "BUY"]
                                ),
                            ),
                            Total_Sell=(
                                "Quantity",
                                lambda x: sum(
                                    x[
                                        df_portfolio_mvmt.loc[x.index, "Action"]
                                        == "SELL"
                                    ]
                                ),
                            ),
                            Net_Quantity=(
                                "Quantity",
                                lambda x: sum(
                                    x[df_portfolio_mvmt.loc[x.index, "Action"] == "BUY"]
                                )
                                - sum(
                                    x[
                                        df_portfolio_mvmt.loc[x.index, "Action"]
                                        == "SELL"
                                    ]
                                ),
                            ),
                            Total_Investment=(
                                "Price",
                                lambda x: sum(
                                    x[df_portfolio_mvmt.loc[x.index, "Action"] == "BUY"]
                                    * df_portfolio_mvmt.loc[x.index, "Quantity"][
                                        df_portfolio_mvmt.loc[x.index, "Action"]
                                        == "BUY"
                                    ]
                                ),
                            ),
                        )
                        .reset_index()
                    )
                    st.title("Summary of Transactions by Ticker")
                    st.dataframe(summary)

                with cols[1]:
                    ticker_counts = (
                        df_portfolio_mvmt["Ticker"].value_counts().reset_index().copy()
                    )
                    ticker_counts.columns = ["Ticker", "Count"]

                    fig_pie = px.pie(
                        ticker_counts,
                        values="Count",
                        names="Ticker",
                        title="Distribution of Transactions by Ticker",
                        hole=0.4,
                    )
                    st.plotly_chart(fig_pie)

            ###################### BUY and SELL Distribution by Ticker ######################
            with st.container(border=True):
                st.title("BUY and SELL Distribution by Ticker")

                transaction_distribution = (
                    df_portfolio_mvmt.groupby(["Ticker", "Action"])
                    .size()
                    .reset_index(name="Count")
                    .copy()
                )

                fig_bar = px.bar(
                    transaction_distribution,
                    x="Ticker",
                    y="Count",
                    color="Action",
                    barmode="group",
                    title="BUY and SELL Distribution by Ticker",
                    labels={"Count": "Number of Transactions", "Ticker": "Ticker"},
                )
                st.plotly_chart(fig_bar)

            ###################### Cash Evolution ######################
            with st.container(border=True):
                df_portfolio_mvmt_cash_graph = (
                    df_portfolio_mvmt.sort_values(by=["Date"])
                    .groupby("Date")
                    .last()
                    .reset_index()
                )

                st.title("Evolution of Cash Over Time")
                fig = go.Figure()

                fig.add_trace(
                    go.Scatter(
                        x=df_portfolio_mvmt_cash_graph["Date"],
                        y=df_portfolio_mvmt_cash_graph["Cash"],
                        mode="lines+markers",
                        name="Cash",
                        line=dict(color="blue"),
                        marker=dict(size=8),
                    )
                )

                fig.update_layout(
                    title="Evolution of Cash Over Time",
                    xaxis_title="Date",
                    yaxis_title="Cash ($)",
                    template="plotly_white",
                    hovermode="x unified",
                )
                st.plotly_chart(fig)

            ###################### Agregate data ######################
            with st.container(border=True):
                df_portfolio_mvmt_period = df_portfolio_mvmt.copy()

                df_portfolio_mvmt_period["Month"] = (
                    df_portfolio_mvmt_period["Date"].dt.to_period("M").astype(str)
                )
                df_portfolio_mvmt_period["Quarter"] = (
                    df_portfolio_mvmt_period["Date"].dt.to_period("Q").astype(str)
                )

                st.title("Aggregate Data by Period")
                tab1, tab2 = st.tabs(["Month", "Quarter"])

                ######## Tab with monthly data ########
                with tab1:
                    cols = st.columns((2, 3))
                    with cols[0]:
                        st.subheader("Aggregate Data by Month")
                        grouped_month = (
                            df_portfolio_mvmt_period.groupby("Month")
                            .agg(
                                Total_Investment=(
                                    "Price",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                        * df_portfolio_mvmt_period.loc[
                                            x.index, "Quantity"
                                        ][
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                    ),
                                ),
                                Total_Quantity_Buy=(
                                    "Quantity",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                    ),
                                ),
                                Total_Quantity_Sell=(
                                    "Quantity",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "SELL"
                                        ]
                                    ),
                                ),
                            )
                            .reset_index()
                        )

                        st.dataframe(grouped_month)
                    with cols[1]:
                        fig_month = px.bar(
                            grouped_month,
                            x="Month",
                            y=["Total_Quantity_Buy", "Total_Quantity_Sell"],
                            title="Transactions by Month",
                            labels={
                                "value": "Quantity",
                                "variable": "Transaction Type",
                            },
                            barmode="stack",
                        )
                        st.plotly_chart(fig_month)

                ######## Tab with quarterly data ########
                with tab2:
                    cols = st.columns((2, 3))
                    with cols[0]:
                        st.subheader("Aggregate Data by Quarter")
                        grouped_quarter = (
                            df_portfolio_mvmt_period.groupby("Quarter")
                            .agg(
                                Total_Investment=(
                                    "Price",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                        * df_portfolio_mvmt_period.loc[
                                            x.index, "Quantity"
                                        ][
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                    ),
                                ),
                                Total_Quantity_Buy=(
                                    "Quantity",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "BUY"
                                        ]
                                    ),
                                ),
                                Total_Quantity_Sell=(
                                    "Quantity",
                                    lambda x: sum(
                                        x[
                                            df_portfolio_mvmt_period.loc[
                                                x.index, "Action"
                                            ]
                                            == "SELL"
                                        ]
                                    ),
                                ),
                            )
                            .reset_index()
                        )

                        st.dataframe(grouped_quarter)

                    with cols[1]:
                        fig_quarter = px.bar(
                            grouped_quarter,
                            x="Quarter",
                            y=["Total_Quantity_Buy", "Total_Quantity_Sell"],
                            title="Transactions by Quarter",
                            labels={
                                "value": "Quantity",
                                "variable": "Transaction Type",
                            },
                            barmode="stack",
                        )
                        st.plotly_chart(fig_quarter)

        ###################### Blockchain data ######################
        with st.expander("Blockchain Monitoring", expanded=False):
            st.subheader("Blockchain Data")
            if block_chain.is_valid():
                st.write("The blockchain is valid.")
            else:
                st.write("The blockchain is not valid.")
            st.write("Below is the raw blockchain data:")
            for i in split_text_by_lines(str(block_chain)):
                st.markdown(
                    f"<div style='font-size:12px; font-family:monospace;'>{i}</div>",
                    unsafe_allow_html=True,
                )
            st.write(f"Blockchain Valid: {block_chain.is_valid()}")

        ###################### Portfolio mov data ######################
        with st.expander("Portfolio Movements (Pure Data)", expanded=False):
            st.subheader("Portfolio Transactions")
            st.dataframe(df_portfolio_mvmt)

    st.write("---")
    st.caption("Streamlit Interface for Backtest Management.")


main()
