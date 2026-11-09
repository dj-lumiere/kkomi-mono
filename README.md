# KNPS Kkomi Mono

국립공원공단의 **국립공원 꼬미체**(KNPS Kkomi)를 에디터와 터미널에서 쓰도록 고정폭으로 바꾼 폰트입니다.

- 라틴 문자와 기호는 한 칸(500), 한글은 두 칸(1000)입니다 (UPM 1000).
- Regular, Italic, Bold, Bold Italic 네 벌이 있습니다.

## 설치

`fonts/` 폴더의 네 파일을 함께 설치합니다.

| 파일 | 굵기 |
|---|---|
| `KNPSKkomiMono-Regular.ttf` | 400 |
| `KNPSKkomiMono-Italic.ttf` | 400, 라틴만 13° 기울임 |
| `KNPSKkomiMono-Bold.ttf` | 700 |
| `KNPSKkomiMono-BoldItalic.ttf` | 700, 라틴만 13° 기울임 |

VS Code 예:

```json
"editor.fontFamily": "'KNPS Kkomi Mono'",
"editor.fontLigatures": true,
"terminal.integrated.fontFamily": "'KNPS Kkomi Mono'"
```

### 웹에서 쓰기

`fonts/woff2/`에 같은 네 벌의 woff2 파일이 있습니다. 하나에 약 1.7MB입니다.

```css
@font-face { font-family: "KNPS Kkomi Mono"; src: url("KNPSKkomiMono-Regular.woff2") format("woff2"); font-weight: 400; font-style: normal; }
@font-face { font-family: "KNPS Kkomi Mono"; src: url("KNPSKkomiMono-Italic.woff2") format("woff2"); font-weight: 400; font-style: italic; }
@font-face { font-family: "KNPS Kkomi Mono"; src: url("KNPSKkomiMono-Bold.woff2") format("woff2"); font-weight: 700; font-style: normal; }
@font-face { font-family: "KNPS Kkomi Mono"; src: url("KNPSKkomiMono-BoldItalic.woff2") format("woff2"); font-weight: 700; font-style: italic; }
code, pre { font-family: "KNPS Kkomi Mono", monospace; }
```

## 원본과 달라진 점

**고정폭**
- 넓은 라틴 문자는 가로로 줄이고 세로획 굵기를 보정했습니다.
- 한글은 두 칸을 채우도록 키우고 획 굵기를 다시 맞췄습니다.
- `*`를 `+ - =`와 같은 높이로 내렸습니다.

**헷갈리기 쉬운 글자**
- `0`에 가운데 점을 넣었습니다.
- `i`에 깃을 달고, `i`와 `l`의 아래를 `t`의 갈고리 모양으로 바꿨습니다.
- `\` 자리에 원화 기호 대신 역슬래시를 넣었습니다.

**한글**
- 원본에서 빈칸이던 8,362자를, 원본 글자의 자모(초성, 모음, 받침)를 떼어 내 조합해 만들었습니다. 이제 11,172자가 모두 있습니다.
- 자모로 분해된 한글(macOS 파일 이름 등)이 완성 음절로 보이도록 조합 규칙을 넣었습니다.

**리거처** (`calt`)
- `->` `<-` `<->` `=>` `<=>` `==` `===` `!=` `!==` `<=` `>=`
- 리거처도 원래 글자 수만큼의 칸을 차지해서, 열이 어긋나지 않습니다.
- `<!--` `====` `<==`처럼 앞뒤에 연산자 글자가 붙으면 리거처가 생기지 않습니다.

**추가한 글자**
- 라틴 확장-A, 악센트 글자, 강세 부호가 붙은 그리스 문자
- 위·아래 첨자, `⑯~⑳` `⒃~⒇` `㈝ ㈞`, 제어 문자 그림 기호(`␀ ␛ ␡` 등)
- 터미널 기호: 박스 선, 블록, 점자, Powerline. 칸에 맞춰 그려서 위아래·좌우가 이어집니다.

**Italic**
- 라틴 문자만 기울이고, 한글은 똑바로 둡니다.
- `a d h m n u`에 갈고리를 달고, `f`는 기준선 아래로 내렸습니다.
- `x`는 `)(` 모양으로 바꿨습니다.

**굵기**
- Regular는 세로획이 대문자 높이의 약 12.5%, Bold는 약 17%가 되도록 획을 고르게 두껍게 했습니다.

## 다시 만들기

Python 3과 `fonttools`, `skia-pathops`가 필요합니다.

```sh
pip install fonttools skia-pathops brotli
cd tools
python make_mono_static.py ../source/KNPSKkomi.otf ../base/KNPSKkomiMono-Base.ttf "KNPS Kkomi" "KNPS Kkomi Mono"
python make_italic.py ../base/KNPSKkomiMono-Base.ttf ../base/KNPSKkomiMono-BaseItalic.ttf
python make_bold.py ../base/KNPSKkomiMono-Base.ttf ../fonts/KNPSKkomiMono-Regular.ttf Regular
python make_bold.py ../base/KNPSKkomiMono-BaseItalic.ttf ../fonts/KNPSKkomiMono-Italic.ttf Italic
python make_bold.py ../base/KNPSKkomiMono-Base.ttf ../fonts/KNPSKkomiMono-Bold.ttf Bold
python make_bold.py ../base/KNPSKkomiMono-BaseItalic.ttf ../fonts/KNPSKkomiMono-BoldItalic.ttf "Bold Italic"
```

woff2는 TTF를 다 만든 뒤 fontTools로 바꿉니다(`TTFont(path).flavor = "woff2"` 후 저장).

첫 단계는 한글 조합 규칙 때문에 2분쯤 걸립니다. `samples/`의 두 파일로 한글, 기호, 리거처, 터미널 기호가 제대로 나오는지 확인할 수 있습니다.

## 라이선스와 출처

- **폰트** (`fonts/`, `base/`, `source/`): 원저작물은 국립공원공단의 국립공원 꼬미체(KNPS Kkomi)입니다(http://www.knps.or.kr). 공공누리 출처표시 조건에 따라 이용하며, 이 폰트를 쓰거나 다시 배포할 때도 같은 출처를 밝혀야 합니다. 바꾼 내용은 `출처.txt`에 정리되어 있습니다.
- **빌드 스크립트** (`tools/`): MIT 라이선스입니다(`tools/LICENSE`).
