"""two_exchange_search.py

2-Exchange (Local Swap) Search Heuristic
========================================

This module implements a simple deterministic (or randomized) hill-climbing style
local search using only 2-exchange (swap) moves constrained to a local neighborhood
window defined by a maximum index distance (``max_distance``).

Neighborhood Definition:
    A neighbor is any layout obtainable by swapping two pieces whose indices i, j
    satisfy: 0 <= i < j < n and 1 <= (j - i) <= max_distance.

Search Strategies Supported:
    - "first_better": Iterate neighbors in a randomized order and accept the first
        strictly improving swap. (First-improvement / stochastic steepest ascent)
    - "best": Evaluate the entire neighborhood, select the best improving swap
        (steepest-ascent). If no improvement exists, terminate.
    - "random_better": Evaluate the full neighborhood, collect all improving swaps,
        then pick one uniformly at random to apply. If none, terminate.

Termination:
    The search stops when no improving neighbor exists (i.e., local optimum under
    the 2-exchange neighborhood) or when ``max_iterations`` (safety cap) is reached.

Integration Notes:
    Fitness evaluation leverages the existing METRIC_REGISTRY and decoder selection
    from ``nesting.config`` to ensure consistency with Simulated Annealing and GA.

Usage Example:
    from nesting.search.two_exchange_search import TwoExchangeSearch
    tes = TwoExchangeSearch(initial_pieces, container, strategy="first_better", max_distance=3)
    best_pieces, best_fitness = tes.run()

Author: Auto-generated helper (requested by user)
"""

from __future__ import annotations
import random
import copy
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Literal, Any

from nesting.core.layout import Piece, Container
from .operations import METRIC_REGISTRY
import nesting.config as config

StrategyName = Literal["first_better", "best", "random_better"]


def _all_local_pairs(n: int, max_distance: int) -> List[Tuple[int, int]]:
    """Return all (i, j) pairs with 0 <= i < j < n and 1 <= j-i <= max_distance."""
    pairs: List[Tuple[int, int]] = []
    for i in range(n - 1):
        upper = min(n - 1, i + max_distance)
        for j in range(i + 1, upper + 1):
            pairs.append((i, j))
    return pairs


@dataclass
class TwoExchangeResult:
    best_pieces: List[Piece]
    best_fitness: float
    iterations: int
    improvements: int
    history: list[tuple[int, float, tuple[int, int]] | tuple[int, float, None]] = field(default_factory=list)


class TwoExchangeSearch:
    """2-Exchange local search restricted to swapping nearby pieces.

    Args:
        pieces: Initial list of pieces (will be deep-copied internally)
        container: Container object for decoding
        strategy: One of {"first_better", "best", "random_better"}
        max_distance: Maximum index gap for a valid swap (default 3)
        max_iterations: Safety upper bound on iterations (default 10_000)
        shuffle_neighbors: If True (default for first_better), randomize neighbor order
            each iteration for diversification.
        allow_rotations: If True, extend the neighbourhood with per-piece rotation
            moves in addition to the windowed swaps. This is a deliberate departure
            from the permutation-only 2-exchange of Gomes & Oliveira, used to give
            the baseline the same access to the rotation space that Random Search
            and the evolutionary methods have. Defaults to False so the faithful
            variant is unchanged.
        rotation_angles: Rotation increments to offer as moves. Defaults to the
            non-zero entries of ``config.ALLOWED_ROTATIONS``. Note ``Piece.rotate``
            is relative and in-place, so with the default ``[0, 180]`` a rotation
            move is a 180 degree toggle of a single piece.
        verbose: If True, print progress logs.
    """

    def __init__(
        self,
        pieces: List[Piece],
        container: Container,
        strategy: StrategyName = "first_better",
        max_distance: int = 3,
        max_iterations: int = 10_000,
        shuffle_neighbors: Optional[bool] = None,
        allow_rotations: bool = False,
        rotation_angles: Optional[List[int]] = None,
        verbose: bool = True,
    ):
        if strategy not in ("first_better", "best", "random_better"):
            raise ValueError(f"Unknown strategy '{strategy}'")

        self.strategy = strategy
        self.max_distance = max_distance
        self.max_iterations = max_iterations
        if shuffle_neighbors is None:
            shuffle_neighbors = (strategy == "first_better")
        self.shuffle_neighbors = shuffle_neighbors
        self.allow_rotations = allow_rotations
        if rotation_angles is None:
            rotation_angles = [a for a in getattr(config, "ALLOWED_ROTATIONS", [0])
                               if a % 360 != 0]
        self.rotation_angles = list(rotation_angles)
        self.verbose = verbose

        # Deep copy initial pieces to avoid mutating caller's list
        self.current_state = [copy.deepcopy(p) for p in pieces]
        self.container = container

        self.metric_fn = METRIC_REGISTRY[config.SELECTED_FITNESS_METRIC]
        self.decoder_name = config.SELECTED_DECODER

        self.current_fitness = self.metric_fn(self.current_state, self.decoder_name, self.container)
        self.best_state = [copy.deepcopy(p) for p in self.current_state]
        self.best_fitness = self.current_fitness

        self.iterations = 0
        self.improvements = 0
        self.history: list[tuple[int, float, tuple[int, int]] | tuple[int, float, None]] = []
        self.history.append((self.iterations, self.current_fitness, None))

    # ------------------------------------------------------------------
    # Core search logic
    # ------------------------------------------------------------------
    def _candidate(self, move) -> List[Piece]:
        """Build the neighbour state for a move without mutating current_state.

        Swap moves only reorder the list, so a shallow copy is safe. Rotation
        moves mutate a Piece in place, so the affected piece is deep-copied
        first -- otherwise evaluating a neighbour would corrupt current_state.
        """
        cand = self.current_state[:]
        kind = move[0]
        if kind == "swap":
            _, i, j = move
            cand[i], cand[j] = cand[j], cand[i]
        elif kind == "rot":
            _, i, angle = move
            rotated = copy.deepcopy(cand[i])
            rotated.rotate(angle)
            cand[i] = rotated
        else:
            raise ValueError(f"Unknown move kind {kind!r}")
        return cand

    def _evaluate_move(self, move) -> float:
        """Return fitness for the neighbour produced by move (non-destructive)."""
        return self.metric_fn(self._candidate(move), self.decoder_name, self.container)

    def _neighbors(self):
        n = len(self.current_state)
        moves = []
        if n >= 2:
            moves.extend(("swap", i, j) for (i, j) in _all_local_pairs(n, self.max_distance))
        if self.allow_rotations:
            moves.extend(("rot", i, a) for i in range(n) for a in self.rotation_angles)
        return moves

    def _log(self, msg: str):
        if self.verbose:
            print(f"[TwoExchangeSearch] {msg}")

    def step(self) -> bool:
        """Perform one iteration. Returns True if improvement applied, else False."""
        moves = self._neighbors()
        if not moves:
            return False

        if self.shuffle_neighbors:
            random.shuffle(moves)

        if self.strategy == "first_better":
            for move in moves:
                fit = self._evaluate_move(move)
                if fit > self.current_fitness:
                    self._apply_move(move, fit)
                    return True
            return False

        # For strategies needing full neighborhood evaluation -----------------
        improvements: list[tuple[float, tuple]] = []  # (fitness, move)
        for move in moves:
            fit = self._evaluate_move(move)
            if fit > self.current_fitness:
                improvements.append((fit, move))

        if not improvements:
            return False

        if self.strategy == "best":
            # Pick highest fitness
            fit, move = max(improvements, key=lambda t: t[0])
            self._apply_move(move, fit)
            return True

        if self.strategy == "random_better":
            fit, move = random.choice(improvements)
            self._apply_move(move, fit)
            return True

        raise RuntimeError("Unreachable strategy path")

    def _apply_move(self, move, new_fitness: float):
        self.current_state = self._candidate(move)
        state = self.current_state
        self.current_fitness = new_fitness
        self.improvements += 1
        if new_fitness > self.best_fitness:
            self.best_fitness = new_fitness
            self.best_state = [copy.deepcopy(p) for p in state]
        self.history.append((self.iterations, new_fitness, move))
        self._log(f"Improved via {move} -> fitness {new_fitness:.6f}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> tuple[List[Piece], float]:
        """Execute the 2-exchange search until local optimum or iteration cap.

        Returns:
            (best_pieces, best_fitness)
        """
        self._log(
            f"Starting search | strategy={self.strategy} | max_distance={self.max_distance} | initial_fitness={self.current_fitness:.6f}"
        )
        while self.iterations < self.max_iterations:
            self.iterations += 1
            improved = self.step()
            if not improved:
                self._log(
                    f"Terminating: local optimum reached after {self.iterations} iterations with best_fitness={self.best_fitness:.6f}"
                )
                break
        return [copy.deepcopy(p) for p in self.best_state], self.best_fitness

    def result(self) -> TwoExchangeResult:
        """Return a detailed result object after running."""
        return TwoExchangeResult(
            best_pieces=[copy.deepcopy(p) for p in self.best_state],
            best_fitness=self.best_fitness,
            iterations=self.iterations,
            improvements=self.improvements,
            history=list(self.history),
        )

__all__ = ["TwoExchangeSearch", "TwoExchangeResult"]
