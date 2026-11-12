# 2.0 실험 스크립트

`docs/2.0-plan.md` 8~9절의 실험입니다. tools/에서 실행하며, 파이썬 환경은 README의 빌드 의존성과 같습니다(pillow, scipy, scikit-image, skan, skia-pathops).

- `recon.py SOURCE.otf OUT_DIR`: 디자이너 글자 2,810자를 중심선 + 펜으로 다시 그려 IoU를 잽니다.
- `consist.py SOURCE.otf OUT_DIR`: 자모별 중심선 구조(끝점, 갈림점 수)의 일관성을 셉니다.
- `context.py SOURCE.otf`: 초성 상자를 모음과 받침 종류로 회귀해 R²와 남는 흔들림을 냅니다.
- `rules.py SOURCE.otf OUT.json`: 지금 조합 방식이 가지런함 규칙 1~3에서 벗어난 정도를 잽니다.
- `compose.py`: 공유 부품으로 11,172자를 조합합니다. `build_comp.py`가 이걸로 make_mono_static을 돌려 시험 글꼴을 만듭니다(그다음 make_kana, make_bold).

## 자모 획 틀 맞추기 (`docs/2.0-plan.md` 11절)

이 스크립트들은 자기 폴더에서 실행합니다. `tools/`는 스스로 찾습니다.

1. `split_capture.py SOURCE.otf split_all.pkl` (tools/에서 실행): hangul_fill이 글자를 초성, 중성, 종성으로 나눈 결과를 저장합니다. 이 결과는 시작 상자로만 씁니다.
2. `frame_prep.py prep.pkl`: 글자마다 뼈대 점(최대 300개), 잉크 구멍, 반 해상도 잉크를 한 번 계산해 둡니다(2,810자에 30초 남짓).
3. `fast_run.py split_all.pkl prep.pkl 1 fit_r1.pkl`: 모든 글자에 자모 틀을 맞춥니다(한 바퀴 3~5분). 다섯째 인자로 앞 바퀴 결과를 주면, 잘 맞은 글자에서 배운 상자와 평균 틀로 다시 맞춥니다. 셋째 인자는 간격(1 = 전부) 또는 글자들입니다.
- `frames.py`: 자모별 손으로 정한 틀(점, 획, 고리), 성공 판정, 배운 틀 계산. `fastfit.py`: 기울기를 식으로 구하는 맞추기. `syl_fit.py`: 시작 상자 중앙값과 배우기(fast_run이 읽어 씁니다).
- `syl_debug.py FITS.pkl [글자] [OUT.png] [init]`: 맞춘 틀을 원본 위에 그립니다(초성 빨강, 중성 파랑, 종성 초록, init이면 시작 위치를 분홍으로).
- `stab.py`: 획의 휨을 값 1개(2차)와 2개(3차)로 두고, 시작 상자를 흔들어 맞춘 값의 흔들림을 비교합니다(`FRAME_BENDS=1|2`).
