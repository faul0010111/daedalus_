"""DAEDALUS — a self-directed architecture for persistent agentic intelligence."""
from .core.runtime import Daedalus, DaedalusConfig
from .experiments.simulations.labyrinth import Labyrinth, LabyrinthConfig

__all__ = ["Daedalus", "DaedalusConfig", "Labyrinth", "LabyrinthConfig"]
__version__ = "0.1.0"
