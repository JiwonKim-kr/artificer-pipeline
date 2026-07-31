# 웹(HTML5) export 실측 기록

> 측정일: 2026-07-30 · 대상 브랜치: `game/gireki-sim` · Godot 4.6.3.stable (Homebrew)
> 목적: NAN2026 제출 조건("링크 접속 → 즉시 플레이, 심사자 입력 0")이 Godot 4 웹
> 빌드로 성립하는지, 그리고 기획서 §5.3 의 CRT 셰이더 전략이 WebGL 에서 유효한지를
> **추정이 아니라 실측**으로 확정한다. (계획 항목 0-b)

## 결론

**성립한다.** 특수 서버 헤더가 필요 없는 정적 호스팅(GitHub Pages·itch.io 등)에서
구동되며, CRT 후처리 셰이더도 WebGL 2 에서 정상 동작한다.

## 확정된 제약과 그 근거

| 항목 | 결정 | 근거(실측) |
|---|---|---|
| 렌더러 | **`gl_compatibility` 고정** | Godot 4.6 웹 플랫폼은 Compatibility(WebGL 2)만 안정 지원. 기본값 `forward_plus` 로는 빌드가 성립하지 않는다. 콘솔 확인: `OpenGL ES 3.0 (WebGL 2.0) - Compatibility` |
| 스레드 | **`variant/thread_support=false`** | 스레드 빌드는 `SharedArrayBuffer` → COOP/COEP 교차출처 격리 헤더가 필수인데, **GitHub Pages 는 커스텀 헤더를 설정할 수 없다.** 미사용 빌드는 헤더 없는 정적 서버에서 구동됨을 확인 (`crossOriginIsolated=false`, `SharedArrayBuffer` 미정의 상태에서 정상 실행) |
| GDExtension | 미지원 | 빌드 구성: `Emscripten 4.0.20, single-threaded, no GDExtension support`. 네이티브 확장에 의존하는 설계를 하지 않는다 |
| 제외 대상 | `exclude_filter` 필수 | `export_filter="all_resources"` 는 프로젝트 전체를 pck 에 담는다. 실측에서 `pipeline/scripts/se_node/node_modules/**`, 그리고 개발용 여론 시뮬(`sim/opinion-model/config.json`)까지 패킹되는 것을 확인 → 파이프라인 스크립트·테스트·문서·정본·개발 시뮬(`sim/`)을 제외. **원칙**: 오프라인/개발 단계 산출물은 런타임 빌드에 절대 넣지 않는다(2계층 아키텍처). 새 개발용 최상위 디렉토리가 생기면 이 필터에 추가할 것 |

## 측정값

| 파일 | raw | gzip |
|---|---|---|
| `index.wasm` | 37,700,666 B (36.0 MB) | 9,382,293 B (8.95 MB) |
| `index.js` | 315,759 B | 78,373 B |
| `index.pck` | 22,400 B | 12,160 B |
| **전송 합계** | | **≈ 9.03 MB** |

- pck 는 `exclude_filter` 적용 전 127,704 B → 적용 후 22,400 B.
- wasm 이 전송량의 99% 이므로 **콘텐츠를 늘려도 초기 로딩은 거의 늘지 않는다.**
  오프라인 베이킹된 콘텐츠 뱅크(텍스트)는 압축이 잘 되므로 용량 리스크가 아니다.
- brotli 는 로컬에 미설치로 미측정. 정적 호스트가 brotli 를 지원하면 더 줄어든다.

## 검증된 CRT 후처리 (기획서 §5.3)

가장 큰 미지수는 화면 후처리 경로(`hint_screen_texture`)의 웹 동작 여부였다.
프로브 씬으로 확인한 결과 **배럴 왜곡 · 스캔라인 · 색수차 · 비네트가 모두 렌더링되고
셰이더 컴파일 에러가 없다.** 필요한 구성:

- `canvas_item` 셰이더 + `uniform sampler2D screen_tex : hint_screen_texture`
- 후처리 `ColorRect` **앞에 `BackBufferCopy`(`copy_mode = 2` = Viewport) 노드**
- 즉 노드 순서: `[화면 내용] → BackBufferCopy → [CRT ColorRect]`

검증에 쓴 프래그먼트 핵심부(파라미터는 art lock 이후 톤에 맞춰 조정):

```glsl
shader_type canvas_item;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform float curvature = 5.0;
uniform float scanline_strength = 0.35;
uniform float aberration = 0.003;
uniform float vignette_strength = 0.7;

void fragment() {
    vec2 cc = SCREEN_UV - 0.5;
    vec2 uv = SCREEN_UV + cc * dot(cc, cc) * (1.0 / curvature);   // 배럴 왜곡
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        COLOR = vec4(0.0, 0.0, 0.0, 1.0);
    } else {
        float r = texture(screen_tex, uv + vec2(aberration, 0.0)).r; // 색수차
        float g = texture(screen_tex, uv).g;
        float b = texture(screen_tex, uv - vec2(aberration, 0.0)).b;
        vec3 col = vec3(r, g, b);
        float rows = 1.0 / max(SCREEN_PIXEL_SIZE.y, 0.0001);
        col *= 1.0 - scanline_strength * (0.5 + 0.5 * sin(uv.y * rows * 3.14159265));
        vec2 vc = uv - 0.5;
        col *= 1.0 - vignette_strength * dot(vc, vc);
        COLOR = vec4(col, 1.0);
    }
}
```

프로브 파일(`scenes/crt_probe.tscn`, `src/tools/probe_*.gdshader`)은 측정 후 삭제했다 —
실제 구현은 승인된 spec 기반으로 `play build` 가 작성한다.

## 게임 빌드 실측 (phase-c · 2026-07-31 추가)

1턴 슬라이스+Phase C 게임을 실제로 export 해 브라우저에서 구동 확인:
- **턴 루프 end-to-end 동작**: 데스크 → 모니터 켜기 → CRT OS 3창(정보원·원고작성·댓글)
  → 문장 취사 → 발행 → 댓글 4세그먼트 반응 + 턴 증가(1/8→2/8). 콘솔 에러 0.
- **CRT 후처리(스캔라인·색수차·곡률·비네트) 웹 렌더 확인** — 0-b 프로브 검증이 실게임에서 재현.
- **한글 폰트 번들 필수(치명 이슈였음)**: 웹 export 에는 시스템 폰트 폴백이 없어 Godot 기본
  폰트(한글 미포함)로는 **한글이 전부 두부(□)** 가 된다. 로컬 에디터는 OS 시스템 폴백이
  가려줘서 발견이 늦었다. 해결: **Neo둥근모**(OFL-1.1, 651,044 B)를 `assets/fonts/` 에 번들하고
  `gui/theme/custom_font` 로 지정 + 픽셀 폰트라 `default_font_antialiasing=0`.
  라이선스 파일(`neodgm_ofl_license.txt`) 동봉 — OFL 은 폰트 재배포 시 라이선스 첨부 요구.
  **교훈: 웹 빌드에서 표시할 모든 문자는 번들 폰트가 커버해야 한다.**
- 폰트 포함 후 전송 합계 gzip ≈ **9.14 MB** (pck raw 172 KB).

## 미결 항목

- **FPS 미측정.** 이 환경(인앱 브라우저)에서는 패널이 백그라운드로 내려가면
  `requestAnimationFrame` 이 스로틀되어 유효한 값을 얻지 못한다. 클릭 반응·전환은
  체감상 즉각적이나 **측정된 값은 없다.** 실기기 브라우저에서 재측정 대상.
- **UI 레이아웃 겹침**: 정보원 창과 여론 게이지 창이 좌하단에서 겹친다(플레이 가능하나
  시각 정리 필요). 아트 reskin/레이아웃 정리 단계에서 해소.

## 재현 방법

```bash
godot --headless --import && godot --headless --export-release "Web"
```

산출물은 `export/web/`(gitignore 대상). 로컬 확인은 헤더를 붙이지 않는 정적 서버로 —
`.claude/launch.json` 의 `web-build` 구성(`python3 -m http.server 8060 --directory export/web`)이
GitHub Pages 와 동일한 조건을 재현한다.

## 참고: export template 설치

Homebrew godot 에는 export template 이 포함되지 않는다. 공식 배포본
`Godot_v4.6.3-stable_export_templates.tpz`(1,255,918,323 B)를 받아
`~/Library/Application Support/Godot/export_templates/4.6.3.stable/` 에 펼쳐 설치했다
(`version.txt` = `4.6.3.stable` 일치 확인). 웹 전용 부분만 받는 공식 경로는 없다.
CI 에서 웹 빌드를 돌리려면 이 설치 단계가 워크플로에 추가되어야 한다.
