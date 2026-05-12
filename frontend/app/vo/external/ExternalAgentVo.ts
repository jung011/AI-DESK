export interface ExternalAgentItem {
  employeeId: string;
  name: string;
  department: string;
  online: boolean;
  skills: string[];
  /** 이 백엔드를 운영하는 본인 여부. true 면 카드에 "(me)" 표시 + [터미널 열기] 버튼 숨김. */
  me: boolean;
}
