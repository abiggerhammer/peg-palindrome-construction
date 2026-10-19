import gzip
import json

import history_zipper_ordinary_tm as hz
from sparse_registered_linker import (
    JsonSparseAdapter,
    SparseRegisteredFabric,
    SymbolicAdapter,
    write_sparse_rows_json_gz,
)
from unary_counter_ordinary_tm import ERROR, READY, machine as counter_machine


def test_sparse_fabric_is_sum_not_product(tmp_path):
    cm = counter_machine()
    adapters = (
        SymbolicAdapter("a", cm, frozenset((READY,)), frozenset((ERROR,))),
        SymbolicAdapter("b", cm, frozenset((READY,)), frozenset((ERROR,))),
    )
    fabric = SparseRegisteredFabric(adapters, controller_states=("S", "T"))
    fabric.register_continuation(fabric.controller_id("T"))
    summary = fabric.summary()
    assert summary["global_states"] == 3 + 2 * (2 + len(cm.states))
    assert summary["global_states"] < len(cm.states) ** 2
    assert summary["global_tapes"] == 2 * (cm.tape_count + 1) + 1


def test_symbolic_history_adapter_preserves_sparse_row_count():
    hm = hz.machine()
    adapter = SymbolicAdapter(
        "hist", hm,
        frozenset(hm.halting_states - {hz.ERROR_STATE}),
        frozenset((hz.ERROR_STATE,)),
    )
    assert sum(1 for _ in adapter.rows()) == len(hm.rows)


def test_json_adapter_reads_reusable_checkpoint_metadata():
    adapter = JsonSparseAdapter("cp", "generated/checkpoint_reusable_table.json.gz")
    assert adapter.state_count == 484699
    assert len(adapter.tape_alphabets) == 64
    assert adapter.result_ready_state_id in adapter.ready_state_ids
    assert adapter.clean_ready_state_id in adapter.ready_state_ids
    assert adapter.result_ready_state_id != adapter.clean_ready_state_id
    first = next(adapter.rows())
    assert first.state_id >= 0
    assert first.next_state_id >= 0


def test_streamed_table_is_valid_json(tmp_path):
    cm = counter_machine()
    adapter = SymbolicAdapter("counter", cm, frozenset((READY,)), frozenset((ERROR,)))
    fabric = SparseRegisteredFabric(adapter and (adapter,), controller_states=("S", "T"))
    fabric.register_continuation(fabric.controller_id("T"))
    path = tmp_path / "fabric.json.gz"
    count = write_sparse_rows_json_gz(
        path, fabric=fabric, rows=fabric.all_service_rows(),
        metadata={"format": "test"},
    )
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    assert len(data["rows_data"]) == count
    assert data["tapes"] == fabric.tape_count
