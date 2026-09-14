import asyncio
from types import FunctionType, SimpleNamespace

from h3_optimizations.comfy_deploy_compat import (
    _build_asset_manager_bridge,
    install_comfy_deploy_execute_compat,
)
from h3_optimizations.comfy_deploy_prompt_hook import register


class _DynPrompt:
    def get_node(self, unique_id):
        return {"class_type": f"Class:{unique_id}"}


class _PromptServer:
    def __init__(self):
        self.handlers = []

    def add_on_prompt_handler(self, handler):
        self.handlers.append(handler)


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


def _deploy_wrapper(origin_execute, handle_execute, *, source="/tmp/ComfyUI/custom_nodes/comfyui-deploy/custom_routes.py"):
    namespace = {
        "__file__": source,
        "origin_execute": origin_execute,
        "handle_execute": handle_execute,
    }
    wrapper = FunctionType(
        _legacy_wrapper.__code__,
        namespace,
        name="swizzle_execute",
        argdefs=_legacy_wrapper.__defaults__,
    )
    wrapper.__qualname__ = "swizzle_execute"
    return wrapper


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


def test_installer_recognizes_exact_deploy_runtime_and_is_idempotent():
    handled = []
    wrapper = _deploy_wrapper(_asset_manager_core, lambda *args: handled.append(args))
    execution_module = SimpleNamespace(execute=wrapper)

    assert install_comfy_deploy_execute_compat(execution_module, emit=None) == "patched"
    patched = execution_module.execute
    assert install_comfy_deploy_execute_compat(execution_module, emit=None) == "already_patched"
    assert execution_module.execute is patched

    server = SimpleNamespace(last_node_id="last")
    asset_manager = object()
    assert asyncio.run(
        patched(
            server,
            _DynPrompt(),
            None,
            "node-1",
            None,
            set(),
            "prompt-1",
            None,
            None,
            None,
            "ui",
            asset_manager,
        )
    ) == ("ui", asset_manager)
    assert handled == [("Class:node-1", "last", "prompt-1", server, "node-1")]


def test_installer_leaves_unrecognized_source_untouched():
    wrapper = _deploy_wrapper(
        _asset_manager_core,
        lambda *args: None,
        source="/tmp/other-node/custom_routes.py",
    )
    execution_module = SimpleNamespace(execute=wrapper)
    assert install_comfy_deploy_execute_compat(execution_module, emit=None) == "not_applicable"
    assert execution_module.execute is wrapper


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


def test_prompt_hook_registers_once_and_preserves_data():
    server = _PromptServer()
    register(server)
    register(server)
    assert len(server.handlers) == 1
    data = {"prompt": {}}
    assert server.handlers[0](data) is data
