shader_type canvas_item;
// CRT 후처리(전체화면 1패스). gl_compatibility(WebGL2)에서 동작 — docs/web-export.md 검증.
// 노드 순서: [화면 내용] → BackBufferCopy(copy_mode=Viewport) → 이 셰이더를 얹은 ColorRect.
// 곡률은 클릭 정합을 위해 약하게(curvature 값이 클수록 왜곡 작음).
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform float curvature = 8.0;
uniform float scanline_strength = 0.25;
uniform float aberration = 0.002;
uniform float vignette_strength = 0.5;

void fragment() {
	vec2 cc = SCREEN_UV - 0.5;
	vec2 uv = SCREEN_UV + cc * dot(cc, cc) * (1.0 / curvature); // 배럴 왜곡
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		COLOR = vec4(0.0, 0.0, 0.0, 1.0);
	} else {
		float r = texture(screen_tex, uv + vec2(aberration, 0.0)).r; // 색수차
		float g = texture(screen_tex, uv).g;
		float b = texture(screen_tex, uv - vec2(aberration, 0.0)).b;
		vec3 col = vec3(r, g, b);
		float rows = 1.0 / max(SCREEN_PIXEL_SIZE.y, 0.0001);
		col *= 1.0 - scanline_strength * (0.5 + 0.5 * sin(uv.y * rows * 3.14159265)); // 스캔라인
		vec2 vc = uv - 0.5;
		col *= 1.0 - vignette_strength * dot(vc, vc); // 비네트
		COLOR = vec4(col, 1.0);
	}
}
