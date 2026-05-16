# PyInstaller 진입 스크립트.
# aidesk_agent.__main__ 자체는 relative import (from .server import ...) 를 쓰는데,
# PyInstaller 는 entry 를 패키지 컨텍스트 없이 실행하므로 absolute import 로 다시 호출한다.
from aidesk_agent.__main__ import main

if __name__ == "__main__":
    main()
