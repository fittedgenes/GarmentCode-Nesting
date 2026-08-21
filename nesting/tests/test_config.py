"""Tests for nesting/config.py"""
import copy
import pytest
import nesting.config as config
from nesting.config import ActiveConfig, load_config, get_stable_hash


@pytest.fixture(autouse=True)
def restore_config():
    """Restore global ACTIVE/SYSTEM after each test."""
    saved = copy.deepcopy(config.ACTIVE)
    saved_sys = copy.deepcopy(config.SYSTEM)
    yield
    config.ACTIVE.__dict__.update(saved.__dict__)
    config.SYSTEM.__dict__.update(saved_sys.__dict__)


def test_load_config_applies_override():
    load_config(container_width_cm=123.0)
    assert config.ACTIVE.container_width_cm == 123.0


def test_load_config_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown configuration"):
        load_config(nonexistent_key=99)


def test_module_alias_reads_active():
    config.ACTIVE.population_size = 42
    assert config.POPULATION_SIZE == 42


def test_stable_hash_changes_with_config():
    h1 = get_stable_hash()
    config.ACTIVE.population_size += 1
    h2 = get_stable_hash()
    assert h1 != h2


def test_stable_hash_reproducible():
    h1 = get_stable_hash()
    h2 = get_stable_hash()
    assert h1 == h2


def test_load_config_dict_override():
    new_weights = {"elites": 0.5, "offspring": 0.5, "mutants": 0, "randoms": 0}
    load_config(population_weights=new_weights)
    assert config.ACTIVE.population_weights["elites"] == 0.5


def test_active_config_defaults_are_sane():
    ac = ActiveConfig()
    assert ac.population_size > 0
    assert ac.num_generations > 0
    assert 0 < ac.mutation_rate < 1
    assert ac.container_width_cm > 0
    assert ac.container_height_cm > 0
