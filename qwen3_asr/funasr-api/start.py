#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FunASR-API Server 启动脚本"""

import sys
import os

# 强制离线模式，必须在任何 HF/transformers 导入前设置
# 注意：不要设置 HF_HUB_OFFLINE=1，否则 vLLM 会把 model_id 替换为绝对路径
os.environ.setdefault("HF_HUB_LOCAL_FILES_ONLY", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def check_and_download_models() -> bool:
    """检查并下载缺失的模型（已强制阉割网络下载逻辑）"""
    # 直接跳过所有检查和下载逻辑，打印提示并放行
    print("\n⚡ 已屏蔽多余的自动下载机制，将直接读取本地指定的模型...")
    return True


def main() -> None:
    """主入口"""
    from app.core.config import settings
    import uvicorn

    workers = int(os.getenv("WORKERS", "1"))

    print(f"🚀 FunASR-API | http://{settings.HOST}:{settings.PORT} | {settings.DEVICE}")

    if workers == 1:
        check_and_download_models()

        try:
            from app.utils.model_loader import preload_models, print_model_statistics
            result = preload_models()
            print_model_statistics(result, use_logger=False)
        except Exception as e:
            print(f"⚠️  预加载失败: {e}")
    else:
        print(f"多Worker模式({workers})，模型延迟加载")

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            workers=workers,
            reload=settings.DEBUG if workers == 1 else False,
            log_level="debug" if settings.DEBUG else settings.LOG_LEVEL.lower(),
            access_log=True,
        )
    except KeyboardInterrupt:
        print("\n已停止")
        sys.exit(0)
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()