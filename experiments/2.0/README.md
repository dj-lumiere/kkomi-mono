# 2.0 실험 스크립트

`docs/2.0-plan.md` 8~9절의 실험입니다. tools/에서 실행하며, 파이썬 환경은 README의 빌드 의존성과 같습니다(pillow, scipy, scikit-image, skan, skia-pathops).

- `recon.py SOURCE.otf OUT_DIR`: 디자이너 글자 2,810자를 중심선 + 펜으로 다시 그려 IoU를 잽니다.
- `consist.py SOURCE.otf OUT_DIR`: 자모별 중심선 구조(끝점, 갈림점 수)의 일관성을 셉니다.
- `context.py SOURCE.otf`: 초성 상자를 모음과 받침 종류로 회귀해 R²와 남는 흔들림을 냅니다.
- `rules.py SOURCE.otf OUT.json`: 지금 조합 방식이 가지런함 규칙 1~3에서 벗어난 정도를 잽니다.
- `compose.py`: 공유 부품으로 11,172자를 조합합니다. `build_comp.py`가 이걸로 make_mono_static을 돌려 시험 글꼴을 만듭니다(그다음 make_kana, make_bold).
