/**
 * 채팅 메시지 markdown 렌더링 — table / code / list / strong / link 등.
 *
 * AI ↔ AI / 사용자 채팅 페이지에서 marked 의 markdown → HTML 변환 후 dompurify
 * 로 sanitize. XSS 차단 + 표 같은 시각 요소 살림.
 *
 * marked 의 옵션:
 *  - breaks: true — 개행 = <br> (메시지 내 줄바꿈 그대로)
 *  - gfm: true — GitHub Flavored Markdown = | table | / ~~strike~~ / [task] 등
 *
 * dompurify sanitize — 기본 profile (script/iframe/event-handler 차단). a tag 의
 * href 는 http(s) 만 허용.
 */
import DOMPurify from 'isomorphic-dompurify';
import { marked } from 'marked';

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function renderMarkdown(src: string): string {
  if (!src) return '';
  try {
    const html = marked.parse(src, { async: false }) as string;
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        'a', 'b', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'hr', 'i', 'li', 'ol', 'p', 'pre', 'strong', 'sub', 'sup',
        'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul', 'del', 's', 'span',
      ],
      ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'class'],
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
    });
  } catch {
    // fallback — markdown parse fail 시 plain text escape
    return src.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
