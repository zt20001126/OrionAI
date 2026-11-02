export type NotificationType = "system";

export interface NotificationRecord {
  id: string;
  userId: string;
  type: NotificationType;
  title: string;
  content: string;
  createdAt: string;
  isRead: boolean;
}
