# nesting/config.py
"""
Organized configuration system for nesting algorithms.
"""

import math
import json
import hashlib
import os
from dataclasses import dataclass, asdict, field
from typing import Literal, Mapping, Dict, Any, Optional, List
from enum import Enum

# ——— Type Definitions ————————————————————————————————————————————————
DecoderName = Literal["BL", "Greedy", "NFP", "Random"]
MetricName = Literal["usage_bb", "concave_hull", "concave_hull_area", "rest_length", "rest_height", "cc_with_rest_height", "cc_with_rest_length", "bb_cc", "bb_cc_area", "bb_with_rest_length"]
CrossoverName = Literal["oxk", "cross_stitch_oxk"]
SortKey = Literal["bbox_area", "hull_area", "aspect_ratio"]
CrossStitchMode = Literal["sticky", "lexicographic"]

class Environment(Enum):
    DEV = "development"
    TEST = "testing" 
    PROD = "production"

# ——— Configuration Classes ————————————————————————————————————————————

@dataclass
class ActiveConfig:
    """Configuration that affects algorithm behavior and reproducibility.
    
    Only these settings influence the stable hash. Changes here require
    new experiment runs for proper comparison.
    """
    # Core algorithm settings
    selected_decoder: DecoderName = "NFP"
    selected_fitness_metric: MetricName = "bb_with_rest_length" 
    selected_crossover: CrossoverName = "cross_stitch_oxk"
    cross_stitch_mode: CrossStitchMode = "lexicographic"
    
    # Container & physical constraints  
    container_width_cm: float = 800
    container_height_cm: float = 140
    seam_allowance_cm: float = 1.0
    samples_per_edge: int = 7
    
    # Genetic algorithm parameters
    population_size: int = 100
    num_generations: int = 20
    mutation_rate: float = 0.2
    force_mutation_on_crossover: bool = False

    # Population composition weights
    population_weights: Dict[str, float] = field(default_factory=lambda: {
        "elites": 0.25, "offspring": 0, "mutants": 0.5, "randoms": 0.25
    })
    
    # Mutation operation weights
    mutation_weights: Dict[str, float] = field(default_factory=lambda: {
        "rotate": 1, "swap": 1, "inversion": 1, "insertion": 1,
        "scramble": 1, "split": 1, "design_params": 1
    })

    zero_gen_rots: bool = True
    
    # Decoder-specific settings
    preserve_holes: bool = True
    nfp_gravitate_on: bool = True
    nfp_edge_samples: int = 5
    gravitate_once: bool = False
    gravitate_step: int = 1
    sort_by: SortKey = "hull_area"
    
    # Fitness metric weights & penalties
    bb_weight: float = 0.5 
    cc_weight: float = 0.5
    
    # Split & design parameter settings
    ox_k: int = 1
    num_splits: int = 1
    split_lower_bound: float = 0.3
    split_upper_bound: float = 0.7
    symmetric_splits: bool = False
    allow_recursive_splits: bool = False
    weight_by_bbox: bool = False
    param_change_margin: float = 0.6
    swap_mutation_k: Optional[int] = None
    
    # Dynamic stopping criteria
    enable_dynamic_stopping: bool = True
    early_stop_window: int = 10
    early_stop_tolerance: float = 0.01
    enable_extension: bool = False
    extend_window: int = 10
    extend_threshold: float = 0.1
    max_generations: int = 20
    
    # Concave hull parameters
    hull_trim_ratio: int = 10
    interior_sample_spacing: int = 5
    boundary_sample_spacing: int = 3
    snap: bool = False
    snap_tolerance: float = 0.1
    
    # Rotation settings
    enable_rotations: bool = True
    allowed_rotations: List[int] = field(default_factory=lambda: [0,180])
    
    # Parameter exclusions for mutations
    excluded_param_paths: List[str] = field(default_factory=lambda: [
        "*meta*", "*.base", "*.level", "*_collar", "*.component.style", 
        "*.cuff.type", "*.panel_curve", "*.num_inserts", "*style_side_cut*",
        "*strapless*", "*sleeveless*", "*enable_asym*", "*flip*", 
        "*standing_shoulder*", "*lapel_standing*", "*sleeve.armhole_shape*",
        "*cut.add*", "*.n_panels", "*panel_curve*"
    ])
    
    def get_stable_hash(self) -> str:
        """Generate reproducible hash based only on algorithmic settings."""
        config_dict = asdict(self)
        # Sort nested dicts for consistency
        for key, value in config_dict.items():
            if isinstance(value, dict):
                config_dict[key] = dict(sorted(value.items()))
        
        config_str = json.dumps(config_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

@dataclass
class SystemConfig:
    """System-level settings that don't affect algorithm results."""
    # System & performance
    multithreading: bool = True
    verbose: bool = True
    
    # File paths
    default_pattern_path: str = "nesting-assets/pattern_files/rand_04ANOD2PBA/rand_04ANOD2PBA_specification.json"
    default_design_param_path: str = "nesting-assets/pattern_files/rand_04ANOD2PBA/rand_04ANOD2PBA_design_params.yaml"  
    default_body_param_path: str = "nesting-assets/pattern_files/rand_04ANOD2PBA/rand_04ANOD2PBA_body_measurements.yaml"
    
    # Logging & experiments
    save_logs: bool = True
    experiments_root: str = "nesting/experiments"
    log_time: bool = True
    log_design_param_paths: bool = False
    save_generation_svgs: bool = True
    
    # Fitness metric parameters (not part of active config hash)
    rest_penalty: float = 0.001
    
    # GUI
    num_copies: int = 0

# ——— Global Configuration Instances ——————————————————————————————————————

ACTIVE = ActiveConfig()
SYSTEM = SystemConfig()

# ——— Configuration Management Functions ——————————————————————————————————

def load_config(env: Environment = Environment.DEV, **overrides) -> ActiveConfig:
    """Load configuration based on environment with optional overrides."""
    global ACTIVE, SYSTEM
    
    if env == Environment.TEST:
        ACTIVE.population_size = 10
        ACTIVE.num_generations = 5
        SYSTEM.save_logs = False
        
    elif env == Environment.PROD:
        ACTIVE.population_size = 200
        ACTIVE.num_generations = 500
        ACTIVE.enable_dynamic_stopping = True
        
    # Apply environment variables
    if metric := os.getenv('NESTING_FITNESS_METRIC'):
        ACTIVE.selected_fitness_metric = metric
    if decoder := os.getenv('NESTING_DECODER'):
        ACTIVE.selected_decoder = decoder
    if pop_size := os.getenv('NESTING_POPULATION_SIZE'):
        ACTIVE.population_size = int(pop_size)
    if generations := os.getenv('NESTING_GENERATIONS'):
        ACTIVE.num_generations = int(generations)
    
    # Apply direct overrides
    for key, value in overrides.items():
        if hasattr(ACTIVE, key):
            setattr(ACTIVE, key, value)
        elif hasattr(SYSTEM, key):
            setattr(SYSTEM, key, value)
        else:
            raise ValueError(f"Unknown configuration setting: {key}")
    
    return ACTIVE

def get_stable_hash() -> str:
    """Get stable hash of current active configuration."""
    return ACTIVE.get_stable_hash()

def get_stable_json() -> str:
    """Get stable JSON of current active configuration."""
    config_dict = asdict(ACTIVE)
    return json.dumps(config_dict, sort_keys=True, separators=(',', ':'))

# ——— Configuration Profiles ——————————————————————————————————————————————

def create_profile(**settings) -> ActiveConfig:
    """Create a configuration profile with custom settings."""
    profile = ActiveConfig()
    for key, value in settings.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
        else:
            raise ValueError(f"Unknown configuration setting: {key}")
    return profile

# Pre-defined profiles
PROFILES = {
    "test": create_profile(
        population_size=20,
        num_generations=2
    ),
    
    "rest_length": create_profile(
        population_size=100,
        num_generations=20,
        selected_fitness_metric="rest_length"
    ),
    
    "usage_bb": create_profile(
        population_size=100,
        num_generations=20,
        selected_fitness_metric="usage_bb"
    ),
    
    "bb_with_rest_length": create_profile(
        population_size=100,
        num_generations=20,
        selected_fitness_metric="bb_with_rest_length"
    )
}

def load_profile(name: str) -> ActiveConfig:
    """Load a pre-defined configuration profile."""
    if name not in PROFILES:
        available = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")
    
    global ACTIVE
    ACTIVE = PROFILES[name]
    return ACTIVE

# ——— Module attribute aliases (live proxies — no sync needed) ————————————
# Accessing config.NFP_EDGE_SAMPLES always reads the current value from ACTIVE.
# Changing ACTIVE.nfp_edge_samples is immediately reflected everywhere.

_ACTIVE_ALIASES: dict = {
    'SELECTED_DECODER':            'selected_decoder',
    'SELECTED_FITNESS_METRIC':     'selected_fitness_metric',
    'SELECTED_CROSSOVER':          'selected_crossover',
    'CROSS_STITCH_MODE':           'cross_stitch_mode',
    'CONTAINER_WIDTH_CM':          'container_width_cm',
    'CONTAINER_HEIGHT_CM':         'container_height_cm',
    'SEAM_ALLOWANCE_CM':           'seam_allowance_cm',
    'SAMPLES_PER_EDGE':            'samples_per_edge',
    'POPULATION_SIZE':             'population_size',
    'NUM_GENERATIONS':             'num_generations',
    'MUTATION_RATE':               'mutation_rate',
    'FORCE_MUTATION_ON_CROSSOVER': 'force_mutation_on_crossover',
    'POPULATION_WEIGHTS':          'population_weights',
    'MUTATION_WEIGHTS':            'mutation_weights',
    'ZERO_GEN_ROTS':               'zero_gen_rots',
    'PRESERVE_HOLES':              'preserve_holes',
    'NFP_GRAVITATE_ON':            'nfp_gravitate_on',
    'NFP_EDGE_SAMPLES':            'nfp_edge_samples',
    'GRAVITATE_ONCE':              'gravitate_once',
    'GRAVITATE_STEP':              'gravitate_step',
    'SORT_BY':                     'sort_by',
    'BB_WEIGHT':                   'bb_weight',
    'CC_WEIGHT':                   'cc_weight',
    'OX_K':                        'ox_k',
    'NUM_SPLITS':                  'num_splits',
    'SPLIT_LOWER_BOUND':           'split_lower_bound',
    'SPLIT_UPPER_BOUND':           'split_upper_bound',
    'SYMMETRIC_SPLITS':            'symmetric_splits',
    'ALLOW_RECURSIVE_SPLITS':      'allow_recursive_splits',
    'WEIGHT_BY_BBOX':              'weight_by_bbox',
    'PARAM_CHANGE_MARGIN':         'param_change_margin',
    'SWAP_MUTATION_K':             'swap_mutation_k',
    'ENABLE_DYNAMIC_STOPPING':     'enable_dynamic_stopping',
    'EARLY_STOP_WINDOW':           'early_stop_window',
    'EARLY_STOP_TOLERANCE':        'early_stop_tolerance',
    'ENABLE_EXTENSION':            'enable_extension',
    'EXTEND_WINDOW':               'extend_window',
    'EXTEND_THRESHOLD':            'extend_threshold',
    'MAX_GENERATIONS':             'max_generations',
    'HULL_TRIM_RATIO':             'hull_trim_ratio',
    'INTERIOR_SAMPLE_SPACING':     'interior_sample_spacing',
    'BOUNDARY_SAMPLE_SPACING':     'boundary_sample_spacing',
    'SNAP':                        'snap',
    'SNAP_TOLERANCE':              'snap_tolerance',
    'ENABLE_ROTATIONS':            'enable_rotations',
    'ALLOWED_ROTATIONS':           'allowed_rotations',
    'EXCLUDED_PARAM_PATHS':        'excluded_param_paths',
}

_SYSTEM_ALIASES: dict = {
    'MULTITHREADING':          'multithreading',
    'VERBOSE':                 'verbose',
    'DEFAULT_PATTERN_PATH':    'default_pattern_path',
    'DEFAULT_DESIGN_PARAM_PATH': 'default_design_param_path',
    'DEFAULT_BODY_PARAM_PATH': 'default_body_param_path',
    'NUM_COPIES':              'num_copies',
    'REST_PENALTY':            'rest_penalty',
    'SAVE_LOGS':               'save_logs',
    'EXPERIMENTS_ROOT':        'experiments_root',
    'LOG_TIME':                'log_time',
    'LOG_DESIGN_PARAM_PATHS':  'log_design_param_paths',
    'SAVE_GENERATION_SVGS':    'save_generation_svgs',
}


# ——— GUI constants ——————————————————————————————————————————————————————
MAX_CANVAS_PX_WIDTH  = 800
MAX_CANVAS_PX_HEIGHT = 600

# Number of random samples for each search heuristic
RANDOM_SEARCH_SAMPLES    = 300
RANDOM_SA_WARMUP_SAMPLES = 200
HEURISTICS_TRIALS        = 100


def __getattr__(name: str):
    if name in _ACTIVE_ALIASES:
        return getattr(ACTIVE, _ACTIVE_ALIASES[name])
    if name in _SYSTEM_ALIASES:
        return getattr(SYSTEM, _SYSTEM_ALIASES[name])
    if name == 'RUNS_DIR':
        return f"{SYSTEM.experiments_root}/runs"
    if name == 'AGGREGATE_DIR':
        return f"{SYSTEM.experiments_root}/aggregate"
    if name == 'SAVE_LOGS_PATH':
        return f"{SYSTEM.experiments_root}/runs/"
    if name == 'GENERATION_PER_FLUSH':
        return max(1, min(math.ceil(100 / ACTIVE.population_size), 10))
    if name == 'LOG_FLUSH_INTERVAL':
        return max(1, min(math.ceil(100 / ACTIVE.population_size), 10))
    raise AttributeError(f"module 'nesting.config' has no attribute {name!r}")


# ——— Legacy Functions ————————————————————————————————————————————————————

def as_dict() -> dict:
    return asdict(ACTIVE)

def stable_config_json() -> str:
    return get_stable_json()

def stable_config_hash() -> str:
    return get_stable_hash()
