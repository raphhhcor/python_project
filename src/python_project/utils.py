# custom_moments.py

import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pybacktestchain.broker import Backtest
from pybacktestchain.data_module import FirstTwoMoments
from scipy.optimize import minimize


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



class CustomBacktest(Backtest):
    def __init__(self, *args, backtest_name: str = None, **kwargs):
        """
        Initialise la sous-classe CustomBacktest avec un attribut supplémentaire `backtest_name`.
        Si `backtest_name` est None, utilise le comportement par défaut de la classe Backtest.

        :param backtest_name: Nom du fichier de backtest.
        :param args: Arguments positionnels pour la classe parent Backtest.
        :param kwargs: Arguments nommés pour la classe parent Backtest.
        """
        super().__init__(*args, **kwargs)  # Initialise la classe mère
        # Si backtest_name est None, utilise la valeur définie par la classe mère
        self.backtest_name = backtest_name if backtest_name is not None else self.backtest_name


def split_text_by_lines(text):
    # Split the text into lines
    lines = text.splitlines()
    # Remove empty lines and strip whitespace
    return [line.strip() for line in lines if line.strip()]