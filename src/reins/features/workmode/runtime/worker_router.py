from reins.features.workmode.runtime.execution_contract import ExecutionContract


class WorkerRouter:

    @staticmethod
    def route_kind(kind: str) -> str:

        ExecutionContract.validate(kind)

        if ExecutionContract.is_visual(kind):
            if kind == "browser_source":
                return "browser"

            if kind == "desktop_capture":
                return "desktop"

        if kind == "ocr":
            return "ocr"

        if kind in {"office_generate", "artifact_present"}:
            return "office"

        if kind in {"wechat_prepare", "confirmation_gate"}:
            return "wechat"

        if kind in {"backend_only", "backend_process", "result_present"}:
            return "backend"

        # 🚨 NO FALLBACK EVER
        raise Exception(f"[ROUTER FAIL] Unknown kind: {kind}")
