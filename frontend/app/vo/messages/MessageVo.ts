/**
 * 백엔드 com.jsh.aidesk.serverapi.messages.vo 와 1:1 대응되는 타입.
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
  createdAt: string;
  deliveredAt: string | null;
  readAt: string | null;
  repliedAt: string | null;
}

export interface MessageListResponse {
  list: MessageItem[];
  hasMore: boolean;
}

export interface MessageCreateRequest {
  fromAgentId: string;
  toAgentId: string;
  content: string;
  replyToMessageId?: string;
}

export interface ConversationItem {
  partnerAgentId: string;
  partnerAgentName: string;
  partnerStatus: 'active' | 'idle' | 'done';
  partnerWorkspaceDir: string;
  lastMessageId: string;
  lastMessageContent: string;
  lastActivityAt: string;
  lastDirection: 'inbox' | 'outbox';
  unreadCount: number;
}

export interface AgentUnread {
  agentId: string;
  agentName: string;
  unread: number;
}

export interface UnreadCountResponse {
  totalUnread: number;
  byAgent: AgentUnread[];
}
