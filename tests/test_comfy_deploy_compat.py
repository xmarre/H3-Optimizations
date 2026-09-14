import asyncio
from types import SimpleNamespace

from h3_optimizations.comfy_deploy_compat import _build_asset_manager_bridge


class _DynPrompt:
    def get_node(self, unique_id):
        return {"class_type": f"Class:{unique_id}"}


async def _legacy_wrapper(
    server,
    dynprompt,
    caches,
    current_item,
    extra_data,
    executed,
    prompt_id,
    execution_list,
    pending_subgraph_results,
    pending_async_nodes,
    ui_outputs=None,
):
    raise AssertionError("legacy wrapper should not run")


async def _asset_manager_core(
    server,
    dynprompt,
    caches,
    current_item,
    extra_data,
    executed,
    prompt_id,
    execution_list,
    pending_subgraph_results,
    pending_async_nodes,
    ui_outputs,
    asset_manager,
):
    return ui_outputs, asset_manager


def test_bridge_forwards_asset_manager_and_preserves_deploy_timing_hook():
    handled = []

    def handle_execute(class_type, last_node_id, prompt_id, server, unique_id):
        handled.append((class_type, last_node_id, prompt_id, server, unique_id))

    bridge = _build_asset_manager_bridge(_legacy_wrapper, _asset_manager_core, handle_execute)
    server = SimpleNamespace(last_node_id="previous")
    asset_manager = object()
    result = asyncio.run(
        bridge(
            server,
            _DynPrompt(),
            None,
            "node-7",
            None,
            set(),
            "prompt-1",
            None,
            None,
            None,
            "ui",
            asset_manager,
        )
    )

    assert result == ("ui", asset_manager)
    assert handled == [("Class:node-7", "previous", "prompt-1", server, "node-7")]


def test_bridge_does_not_fabricate_completion_after_core_error():
    handled = []

    async def failing_core(
        server,
        dynprompt,
        caches,
        current_item,
        extra_data,
        executed,
        prompt_id,
        execution_list,
        pending_subgraph_results,
        pending_async_nodes,
        ui_outputs,
        asset_manager,
    ):
        raise RuntimeError("core failure")

    bridge = _build_asset_manager_bridge(_legacy_wrapper, failing_core, lambda *args: handled.append(args))
    server = SimpleNamespace(last_node_id=None)

    try:
        asyncio.run(
            bridge(
                server,
                _DynPrompt(),
                None,
                "node",
                None,
                set(),
                "prompt",
                None,
                None,
                None,
                None,
                object(),
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "core failure"
    else:
        raise AssertionError("expected core failure")

    assert handled == []
