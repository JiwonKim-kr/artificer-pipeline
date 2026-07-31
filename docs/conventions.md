# 컨벤션 v1.0

## 파일/디렉토리 네이밍

- 디렉토리·파일: `snake_case` (Godot 권장)
- 씬: `player.tscn`, `main_menu.tscn` — 파일명은 루트 노드 이름의 snake_case
- 노드 이름: `PascalCase` (예: `Player`, `HealthBar`)
- 스크립트: 대응 씬과 동일한 이름 (`player.gd`)
- 스프라이트: `assets/art/sprites/<카테고리>/<이름>_<상태>_<프레임>.png`
  예: `enemy/slime_idle_00.png`
- UI 아트: `assets/art/ui/<화면>/<요소>.png`
- 효과음: `assets/audio/se/<이벤트>.ogg` 예: `player_jump.ogg`, `ui_confirm.ogg`
- 플레이스홀더: `PLACEHOLDER_` 접두사 필수. 예: `PLACEHOLDER_slime_idle.png`
- 셰이더: `src/ui/shaders/<이름>.gdshader` (snake_case). 예: `crt_screen.gdshader`. ShaderMaterial 리소스는 `<이름>_material.tres`
- 폰트: `assets/fonts/<이름>.ttf` + 라이선스 텍스트 동봉(예: `neodgm_ofl_license.txt`).
  웹 export 는 시스템 폰트 폴백이 없으므로 표시할 모든 문자(한글 포함)는 번들 폰트가 커버해야 한다

## 매니페스트 ID 규칙

`<track>:<카테고리>/<이름>` 형식. 예: `art:enemy/slime_idle`, `se:player_jump`

## 오디오 규격

- 포맷: OGG Vorbis
- SE: 모노 허용, -16 LUFS 정규화
- BGM: 스테레오, -14 LUFS, 루프 포인트 메타데이터 필수

## 이미지 규격

- PNG, 투명 배경 (스프라이트/UI)
- 스프라이트시트는 프레임 크기 일정, 매니페스트에 프레임 정보 기록

## 커밋 규칙

- 명령 단위로 커밋: `[play build] 점프 메커닉 구현` / `[art gen] 슬라임 idle 스프라이트`
- `src/core/` 변경 커밋에는 승인된 spec 문서 경로를 본문에 명시
