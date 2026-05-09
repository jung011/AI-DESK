<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">실행 로그</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>실행 로그</em></a>
      </div>
    </div>

    <div class="placeholder">
      <p class="title">실행 로그 화면은 후속 단계에 구현됩니다.</p>
      <p class="desc">Claude Code CLI 세션 로그 + JSONL 컨텍스트 분석 + 에이전트 활동 타임라인을 한 곳에서 보여줄 예정입니다.</p>
    </div>
  </div>
</template>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.tit_h2 { font-size: 20px; font-weight: 700; color: #101010; margin: 0; }
.descList_pageLocation {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #94A3B8;
}
.descList_pageLocation a { color: #94A3B8; text-decoration: none; }
.descList_pageLocation a + a::before {
  content: '›'; margin-right: 6px; color: #CBD5E1;
}
.descList_pageLocation em { font-style: normal; color: #475569; font-weight: 600; }

.placeholder {
  background: #fff;
  border: 1px dashed #D4DCE4;
  border-radius: 10px;
  padding: 60px 28px;
  text-align: center;
}
.placeholder .title {
  font-size: 14px; font-weight: 600; color: #475569;
  margin: 0 0 8px;
}
.placeholder .desc {
  font-size: 13px; color: #94A3B8;
  margin: 0; line-height: 1.6;
}
</style>
