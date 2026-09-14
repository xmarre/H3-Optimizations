"""Local compatibility bridge for Comfy Deploy's legacy execute wrapper.

This module deliberately does not patch ComfyUI or Comfy Deploy source files.  It
repairs only one already-installed runtime shape: Comfy Deploy's legacy
``swizzle_execute`` wrapper around a newer ComfyUI ``execution.execute`` that
requires the trailing ``asset_manager`` argument.

The bridge is fail-closed.  Any different wrapper/source/signature is left
untouched so future Comfy Deploy or ComfyUI changes cannot be silently guessed.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

_BROKEN_WRAPPER_PARAMETERS = (
    "server",
    "dynprompt",
    "caches",
    "current_item",
    "extra_data",
    "executed",
    "prompt_id",
    "execution_list",
    "pending_subgraph_results",
    "pending_async_nodes",
    "ui_outputs",
)
_CORE_ASSET_MANAGER_PARAMETERS = (*_BROKEN_WRAPPER_PARAMETERS, "asset_manager")
_PATCH_MARKER = "_h3_optimizations_comfy_deploy_asset_manager_compat_v1"


def _parameter_names(function: Any) -> tuple[str, ...] | None:
    try:
        return tuple(inspect.signature(function, follow_wrapped=False).parameters)
    except (TypeError, ValueError):
        return None


def _is_comfy_deploy_custom_routes(globals_dict: dict[str, Any]) -> bool:
    source = globals_dict.get("__file__")
    if not isinstance(source, str):
        return False
    path = Path(source)
    parent = path.parent.name.lower().replace("_", "-")
    return path.name == "custom_routes.py" and parent == "comfyui-deploy"


def _build_asset_manager_bridge(
    current: Callable[..., Any],
    origin_execute: Callable[..., Any],
    handle_execute: Callable[..., Any],
):
    async def swizzle_execute(
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
        # Preserve Comfy Deploy's timing hook exactly; only forward the newly
        # required ComfyUI ABI argument that the legacy wrapper drops.
        unique_id = current_item
        class_type = dynprompt.get_node(unique_id)["class_type"]
        last_node_id = server.last_node_id

        result = await origin_execute(
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
        )

        handle_execute(class_type, last_node_id, prompt_id, server, unique_id)
        return result

    swizzle_execute.__module__ = getattr(current, "__module__", swizzle_execute.__module__)
    swizzle_execute.__qualname__ = getattr(current, "__qualname__", swizzle_execute.__qualname__)
    swizzle_execute.__doc__ = getattr(current, "__doc__", None)
    swizzle_execute.__dict__.update(getattr(current, "__dict__", {}))
    setattr(swizzle_execute, _PATCH_MARKER, True)
    return swizzle_execute


def install_comfy_deploy_execute_compat(
    execution_module: Any | None = None,
    *,
    emit: Callable[[str], Any] | None = print,
) -> str:
    """Repair the one known Comfy Deploy/ComfyUI ``execution.execute`` ABI gap.

    Returns ``patched``, ``already_patched`` or ``not_applicable``.  No source
    files are modified and unsupported runtime shapes are intentionally ignored.
    """

    if execution_module is None:
        try:
            execution_module = importlib.import_module("execution")
        except ModuleNotFoundError:
            return "not_applicable"

    current = getattr(execution_module, "execute", None)
    if not callable(current):
        return "not_applicable"
    if getattr(current, _PATCH_MARKER, False) is True:
        return "already_patched"
    if not asyncio.iscoroutinefunction(current):
        return "not_applicable"
    if getattr(current, "__name__", None) != "swizzle_execute":
        return "not_applicable"
    if _parameter_names(current) != _BROKEN_WRAPPER_PARAMETERS:
        return "not_applicable"

    globals_dict = getattr(current, "__globals__", None)
    if not isinstance(globals_dict, dict) or not _is_comfy_deploy_custom_routes(globals_dict):
        return "not_applicable"

    origin_execute = globals_dict.get("origin_execute")
    handle_execute = globals_dict.get("handle_execute")
    if not asyncio.iscoroutinefunction(origin_execute) or not callable(handle_execute):
        return "not_applicable"
    if _parameter_names(origin_execute) != _CORE_ASSET_MANAGER_PARAMETERS:
        return "not_applicable"

    execution_module.execute = _build_asset_manager_bridge(current, origin_execute, handle_execute)
    if emit is not None:
        emit(
            "[H3 Optimizations] runtime compatibility: bridged Comfy Deploy "
            "execution.execute to ComfyUI's asset_manager ABI"
        )
    return "patched"


__all__ = ["install_comfy_deploy_execute_compat"]
