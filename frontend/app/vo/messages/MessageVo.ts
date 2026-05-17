/**
 * 백엔드 com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo 대응.
 */
export type MessageStatus = 'sent' | 'delivered' | 'replied' | 'failed';

export interface MessageItem {
  messageId: string;
  fromAgentId: string;
  fromAgentName: string;
  toAgentId: string;
  toAgentName: string;
  content: string;
  replyToMessageId: string | null;
  status: MessageStatus;
  errorReason: string | null;
  createdAt: string;          // ISO 8601
  deliveredAt: string | null;
  readAt: string | null;
  repliedAt: string | null;
}

export interface MessageCreateRequest {
  fromAgentId: string;
  toAgentId: string;
  content: string;
  replyToMessageId?: string;
}
