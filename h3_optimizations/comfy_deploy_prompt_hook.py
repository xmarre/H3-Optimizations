"""Register a prompt-boundary check for the local Comfy Deploy compatibility bridge."""

from .comfy_deploy_compat import install_comfy_deploy_execute_compat


def register(prompt_server):
    marker = "_h3_optimizations_comfy_deploy_prompt_hook_v1"
    if getattr(prompt_server, marker, None) is not None:
        return

    def before_prompt(data):
        install_comfy_deploy_execute_compat()
        return data

    prompt_server.add_on_prompt_handler(before_prompt)
    setattr(prompt_server, marker, before_prompt)
