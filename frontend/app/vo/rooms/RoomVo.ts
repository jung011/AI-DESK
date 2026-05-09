export interface RoomMemberRef {
  agentId: string;
  agentName: string;
  role: 'coordinator' | 'member';
  joinedAt: string;
}

export interface RoomItem {
  roomId: string;
  roomName: string;
  createdBy: string;
  createdByName: string;
  createdAt: string;
  archivedAt: string | null;
  members: RoomMemberRef[];
}

export interface RoomCreateRequest {
  roomName: string;
  createdBy: string;
  initialMemberAgentIds?: string[];
}

export interface RoomMessageItem {
  messageId: string;
  roomId: string;
  fromAgentId: string;
  fromAgentName: string;
  content: string;
  createdAt: string;
}

export interface RoomMessageCreateRequest {
  fromAgentId: string;
  content: string;
}
