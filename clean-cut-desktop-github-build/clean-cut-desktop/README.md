# 깔끔컷 1.0 — Windows용 AI 배경 제거 프로그램

## 무엇이 구현되어 있나요?

- 무료 **rembg U2NetP** 모델로 자동 배경 제거
- 수동 **지우개** / **복원 브러시**, 크기(1~200px), 강도(1~100%)
- 마우스 휠 대신 10~800% **확대 슬라이더**, `Ctrl+Z` 실행 취소, `Ctrl+Y` 다시 실행
- 한 장 또는 여러 장 **AI 순차 처리**, 모든 이미지 폴더에 저장
- 배경색: 투명 / 흰색 / 파란색 / 검정 / 사용자 지정
- 이미지 출력 비율: 원본, 1:1, 4:5, 16:9, 9:16, A4 세로
- 이미지 출력 너비 조절, PNG 또는 JPG 내보내기

**참고:** 복원 브러시는 원본의 픽셀을 다시 보여주는 방식입니다. 수동 지우기 전에 AI가 완전히 제거한 대상도 복원할 수 있습니다. 자동 AI 재제거/선택 영역 AI 리터칭은 이 버전에 포함되어 있지 않습니다.

## EXE 제작(Windows 10/11)

1. Windows PC에 **Python 3.11 (64-bit)** 설치: https://www.python.org/downloads/ (설치 시 PATH 옵션 선택 권장).
2. 프로젝트 ZIP 압축 해제.
3. `Windows_EXE_만들기.bat` 더블클릭. Python 패키지 설치 + AI 모델 다운로드 + Windows 실행 파일 생성이 진행됩니다. **이 과정에만 인터넷이 필요합니다.**
4. 완성된 `dist\CleanCut\CleanCut.exe` 실행.
5. 다른 직원에게 배포할 때는 **`dist\CleanCut` 폴더 전체**를 ZIP으로 묶어 전달합니다. EXE 하나만 복사하지 마세요. 사용자 PC에는 Python이 필요 없습니다.

EXE는 폴더형 배포 방식으로 제작됩니다. 일반적인 '다음 → 설치' 마법사형 Setup.exe는 포함하지 않습니다. 모델을 함께 묶어 만든 결과물은 인터넷 없이 실행할 수 있도록 설계했습니다.

## 소스 실행

`Windows_실행.bat`을 실행합니다. 첫 AI 처리 때 모델 다운로드가 필요할 수 있습니다.

## 주의사항

- AI 처리 시간과 정확도는 컴퓨터 사양과 사진 내용에 따라 달라집니다.
- 큰 사진을 여러 장 처리하면 메모리 사용량이 늘어날 수 있습니다.
- PNG는 투명 배경을 보존합니다. JPG는 투명을 지원하지 않으므로 흰색으로 합성합니다.
- 이 아카이브에는 Python 소스와 Windows 빌드 스크립트가 포함되어 있으며 **이미 만들어진 Windows EXE는 포함되지 않습니다.**
- 서명되지 않은 EXE는 Windows SmartScreen 경고를 표시할 수 있습니다.
- 사용 오픈소스: rembg(MIT), PySide6(LGPL/GPL/상용 이중 라이선스), Pillow, NumPy, ONNX Runtime, PyInstaller. 회사 배포 시 각 라이선스 조건을 확인하세요.

## PC에 Python 설치 없이 Windows EXE 빌드 (GitHub Actions)

이 프로젝트에는 `.github/workflows/build-windows.yml`이 포함됩니다.

1. GitHub에 새 저장소를 만들고 **압축 해제한 프로젝트 폴더의 내용 전체**를 업로드합니다. `.github` 폴더도 포함해야 합니다. (GitHub 웹 업로드 시 숨김 폴더 업로드가 누락되면 GitHub Desktop이나 Git 명령을 사용할 수 있습니다.)
2. GitHub 저장소의 **Actions → Build CleanCut Windows EXE → Run workflow**를 클릭합니다.
3. 실행이 성공하면 해당 실행 결과의 **Artifacts → CleanCut-Windows**를 다운로드합니다.
4. 받은 압축 파일 안의 `CleanCut-Windows.zip`을 다시 풀고 `CleanCut.exe`를 실행합니다. EXE와 동봉된 `_internal` 폴더를 함께 유지해야 합니다.

이 빌드는 GitHub의 Windows 가상 컴퓨터에서 진행하므로 사용하는 PC에 Python 설치가 필요하지 않습니다. 다만 GitHub 계정 및 저장소 접근 권한이 필요하며, 빌드 성공 여부는 실제 실행 후 확인해야 합니다. 라이선스 및 회사 보안 정책도 검토하세요.
