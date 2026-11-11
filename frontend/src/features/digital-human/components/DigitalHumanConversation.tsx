import { useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { t } from "../../../i18n/localeStore";
import type {
  ConversationMessage,
  ImageResultContentPart,
  KlineChartContentPart,
  KlineChartPayload,
  KlineMovingAverage,
  QuestionAnswersContentPart,
  QuestionContentPart,
  VideoResultContentPart,
  PlaceCardsPayload,
} from "../../conversations/conversationApi";
import { CompletedQuestionCard, QuestionAnswerCard } from "../../conversations/QuestionAnswerCards";
import { QuestionWizard } from "../../conversations/QuestionWizard";

/** 展示周边搜索结果中的商家资料；调用方：数字人消息列表。 */
function PlaceCards({ data }: { data: PlaceCardsPayload }) {
  return (
    <section aria-label={data.title} className="digital-human-place-cards">
      <h3>
        {data.title}（{data.total}家）
      </h3>
      {data.places.map((place) => (
        <article className="digital-human-place-card" key={place.id}>
          <header>
            <strong>{place.name}</strong>
            {place.rating !== null && (
              <span className="digital-human-place-card__rating">★ {place.rating.toFixed(1)}</span>
            )}
          </header>
          <div className="digital-human-place-card__details">
            <span>{place.address}</span>
            <span>约 {place.distance} 米</span>
            {place.tel && <a href={`tel:${place.tel}`}>{place.tel}</a>}
            {place.business_hours && <span>营业时间 {place.business_hours}</span>}
          </div>
        </article>
      ))}
    </section>
  );
}

interface DigitalHumanConversationProps {
  messages: ConversationMessage[];
  pendingMessage: string | null;
  pendingQuestionMessageId: string | null;
  currentQuestionIndex: number;
  selectedAnswers: Record<string, string>;
  streamedAssistantText: string;
  streamedKlineChart: KlineChartPayload | null;
  streamedPlaceCards: PlaceCardsPayload | null;
  onQuestionAnswerSelect: (questionId: string, answer: string) => void;
  onQuestionNext: () => void;
  onQuestionPrevious: () => void;
  onQuestionSubmit: () => void;
  isSubmitting: boolean;
  isLoading: boolean;
}

function getText(message: ConversationMessage): string {
  return message.content.parts
    .filter(
      (part): part is Extract<(typeof message.content.parts)[number], { type: "text" }> =>
        part.type === "text",
    )
    .map((part) => part.text)
    .join("\n");
}

/** 提取消息中的生图结果，供数字人对话气泡展示。 */
function getImageResults(message: ConversationMessage): ImageResultContentPart[] {
  return message.content.parts.filter(
    (part): part is ImageResultContentPart => part.type === "image_result",
  );
}

/** 提取视频结果，供数字人对话播放器展示。 */
function getVideoResults(message: ConversationMessage): VideoResultContentPart[] {
  return message.content.parts.filter(
    (part): part is VideoResultContentPart => part.type === "video_result",
  );
}

/** 从消息中读取K线数据，供历史展示与流式完成态图表绘制。 */
function getKlineChart(message: ConversationMessage): KlineChartContentPart | null {
  return (
    message.content.parts.find(
      (part): part is KlineChartContentPart => part.type === "kline_chart",
    ) ?? null
  );
}

/** 绘制 OHLC 蜡烛及用户请求的均线；输入图表 payload；输出 SVG 图表；调用方：数字人对话消息。 */
function KlineChart({ chart }: { chart: KlineChartPayload }) {
  const width = 600;
  const plotTop = 18;
  const plotBottom = 185;
  const movingAverages = chart.moving_averages ?? [];
  const movingAverageValues = movingAverages.flatMap((series) =>
    series.values.filter((value): value is number => value !== null),
  );
  const lows = [...chart.candles.map((candle) => candle.low), ...movingAverageValues];
  const highs = [...chart.candles.map((candle) => candle.high), ...movingAverageValues];
  let minPrice = Math.min(...lows);
  let maxPrice = Math.max(...highs);
  if (minPrice === maxPrice) {
    const padding = maxPrice * 0.01;
    minPrice -= padding;
    maxPrice += padding;
  }
  const y = (price: number) =>
    plotBottom - ((price - minPrice) / (maxPrice - minPrice)) * (plotBottom - plotTop);
  const step = (width - 48) / chart.candles.length;
  const candleWidth = Math.min(6, step * 0.7);
  const periodLabel = { daily: "日K", weekly: "周K", monthly: "月K" }[chart.period];
  const movingAverageClasses: Record<KlineMovingAverage["period"], string> = {
    5: "digital-human-kline__moving-average--5",
    10: "digital-human-kline__moving-average--10",
    20: "digital-human-kline__moving-average--20",
    60: "digital-human-kline__moving-average--60",
  };

  return (
    <figure className="digital-human-kline">
      <figcaption>
        <strong>
          {chart.name}（{chart.code}）
        </strong>
        <span>{periodLabel} · 前复权</span>
      </figcaption>
      <svg
        aria-label={`${chart.name} ${periodLabel} K线图，${chart.start_date} 至 ${chart.end_date}，前复权`}
        className="digital-human-kline__chart"
        role="img"
        viewBox={`0 0 ${width} 220`}
      >
        {[0, 0.5, 1].map((ratio) => {
          const gridY = plotTop + (plotBottom - plotTop) * ratio;
          const price = maxPrice - (maxPrice - minPrice) * ratio;
          return (
            <g key={ratio}>
              <line className="digital-human-kline__grid" x1="42" x2="598" y1={gridY} y2={gridY} />
              <text className="digital-human-kline__axis-label" x="0" y={gridY + 4}>
                {price.toFixed(2)}
              </text>
            </g>
          );
        })}
        {chart.candles.map((candle, index) => {
          const centerX = 44 + step * (index + 0.5);
          const rising = candle.close >= candle.open;
          const bodyTop = Math.min(y(candle.open), y(candle.close));
          const bodyHeight = Math.max(1, Math.abs(y(candle.open) - y(candle.close)));
          return (
            <g
              className={
                rising ? "digital-human-kline__candle--up" : "digital-human-kline__candle--down"
              }
              key={candle.date}
            >
              <line x1={centerX} x2={centerX} y1={y(candle.high)} y2={y(candle.low)} />
              <rect
                height={bodyHeight}
                width={candleWidth}
                x={centerX - candleWidth / 2}
                y={bodyTop}
              />
            </g>
          );
        })}
        {movingAverages.map((series) => {
          const points = series.values.flatMap((value, index) =>
            value === null ? [] : [{ x: 44 + step * (index + 0.5), y: y(value) }],
          );
          const className = `digital-human-kline__moving-average ${movingAverageClasses[series.period]}`;
          if (points.length === 0) return null;
          if (points.length === 1) {
            return (
              <circle
                className={className}
                cx={points[0].x}
                cy={points[0].y}
                key={series.period}
                r="2"
              />
            );
          }
          return (
            <polyline
              className={className}
              fill="none"
              key={series.period}
              points={points.map((point) => `${point.x},${point.y}`).join(" ")}
            />
          );
        })}
      </svg>
      {movingAverages.length > 0 && (
        <div aria-label="均线图例" className="digital-human-kline__legend" role="group">
          {movingAverages.map((series) => (
            <span className="digital-human-kline__legend-item" key={series.period}>
              <span
                aria-hidden="true"
                className={`digital-human-kline__legend-line ${movingAverageClasses[series.period]}`}
              />
              MA{series.period}
            </span>
          ))}
        </div>
      )}
      <div aria-hidden="true" className="digital-human-kline__dates">
        <span>{chart.start_date}</span>
        <span>{chart.end_date}</span>
      </div>
      <p className="digital-human-kline__source">数据来源：{chart.source}</p>
    </figure>
  );
}

/** 播放当前用户的视频结果；输入视频消息，输出带控制栏的播放器。 */
function DigitalHumanVideoResult({ part }: { part: VideoResultContentPart }) {
  const [hasError, setHasError] = useState(false);
  if (hasError) return <p role="status">{t("生成视频暂时无法播放。")}</p>;
  return (
    <video
      className="digital-human-video-result"
      controls
      preload="metadata"
      aria-label={t("AI 生成的视频")}
      onError={() => setHasError(true)}
      src={part.video_url}
    />
  );
}

/** 展示数字人生成的私有图片缩略图，并提供查看原图入口。 */
function DigitalHumanImageResult({ part }: { part: ImageResultContentPart }) {
  const [hasError, setHasError] = useState(false);
  if (hasError) {
    return (
      <p className="digital-human-image-result__status" role="status">
        {t("生成图片暂时无法显示。")}
      </p>
    );
  }
  return (
    <figure className="digital-human-image-result">
      <a
        aria-label={t("查看生成图片原图")}
        href={part.image_url}
        rel="noopener noreferrer"
        target="_blank"
      >
        <img alt={t("AI 生成的图片")} onError={() => setHasError(true)} src={part.image_url} />
      </a>
    </figure>
  );
}

/** 判断持久化历史是否已包含当前临时用户消息，避免刷新交界时重复显示；调用方：数字人消息列表。 */
function hasPersistedPendingMessage(
  messages: ConversationMessage[],
  pendingMessage: string,
): boolean {
  return messages.some(
    (message) => message.role === "user" && getText(message).trim() === pendingMessage.trim(),
  );
}

function getQuestionPart(message: ConversationMessage): QuestionContentPart | null {
  return (
    message.content.parts.find((part): part is QuestionContentPart => part.type === "question") ??
    null
  );
}

/** 获取消息中已提交的题卡答案；输入为会话消息，输出供已答卡片展示。 */
function getQuestionAnswersPart(message: ConversationMessage): QuestionAnswersContentPart | null {
  return (
    message.content.parts.find(
      (part): part is QuestionAnswersContentPart => part.type === "question_answers",
    ) ?? null
  );
}

/**
 * 渲染会话历史和当前流式回复；输入消息、流式文本／图表、题卡状态及操作回调和加载状态；
 * 输出会话消息区域；调用方：数字人会话页面。
 */
export function DigitalHumanConversation({
  messages,
  pendingMessage,
  pendingQuestionMessageId,
  currentQuestionIndex,
  selectedAnswers,
  streamedAssistantText,
  streamedKlineChart,
  streamedPlaceCards,
  onQuestionAnswerSelect,
  onQuestionNext,
  onQuestionPrevious,
  onQuestionSubmit,
  isSubmitting,
  isLoading,
}: DigitalHumanConversationProps) {
  const messageListRef = useRef<HTMLDivElement>(null);
  const showPendingMessage =
    pendingMessage !== null && !hasPersistedPendingMessage(messages, pendingMessage);
  const streamedChartAlreadySaved = streamedKlineChart
    ? messages.some((message) => {
        const savedChart = getKlineChart(message)?.content;
        return (
          savedChart?.code === streamedKlineChart.code &&
          savedChart.period === streamedKlineChart.period &&
          savedChart.start_date === streamedKlineChart.start_date &&
          savedChart.end_date === streamedKlineChart.end_date
        );
      })
    : false;
  const visibleStreamedChart = streamedChartAlreadySaved ? null : streamedKlineChart;

  useLayoutEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) messageList.scrollTop = messageList.scrollHeight;
  }, [isLoading, messages, pendingMessage, streamedAssistantText, visibleStreamedChart]);

  return (
    <div
      aria-label={t("对话消息")}
      className="digital-human-messages"
      role="log"
      aria-live="polite"
      ref={messageListRef}
    >
      {messages.map((message, index) => {
        const text = getText(message);
        const imageResults = getImageResults(message);
        const videoResults = getVideoResults(message);
        const klineChart = getKlineChart(message);
        const placeCards = message.content.parts.find((part) => part.type === "place_cards");
        const questionPart = getQuestionPart(message);
        const questionAnswersPart = getQuestionAnswersPart(message);
        const isPendingQuestion = pendingQuestionMessageId === message.id;
        const nextMessage = messages[index + 1];
        const hasSubmittedQuestionAnswers =
          questionPart !== null &&
          nextMessage?.role === "user" &&
          (getQuestionAnswersPart(nextMessage) !== null ||
            getText(nextMessage).startsWith("用户已提交以下选择："));
        if (
          !text &&
          imageResults.length === 0 &&
          videoResults.length === 0 &&
          !klineChart &&
          !placeCards &&
          !questionPart &&
          !questionAnswersPart
        )
          return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}${questionPart ? " digital-human-message--question" : ""}${questionAnswersPart ? " digital-human-message--question-answers" : ""}`}
            key={message.id}
          >
            {text && !questionAnswersPart && (
              <div className="digital-human-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
              </div>
            )}
            {imageResults.map((part) => (
              <DigitalHumanImageResult key={part.task_result_id} part={part} />
            ))}
            {videoResults.map((part) => (
              <DigitalHumanVideoResult key={part.task_result_id} part={part} />
            ))}
            {klineChart && <KlineChart chart={klineChart.content} />}
            {placeCards?.type === "place_cards" && <PlaceCards data={placeCards.data} />}
            {questionAnswersPart && <QuestionAnswerCard items={questionAnswersPart.items} />}
            {questionPart && isPendingQuestion && (
              <QuestionWizard
                currentIndex={currentQuestionIndex}
                isSubmitting={isSubmitting}
                messageId={message.id}
                onNext={onQuestionNext}
                onPrevious={onQuestionPrevious}
                onSelect={onQuestionAnswerSelect}
                onSubmit={onQuestionSubmit}
                questions={questionPart.questions}
                selectedAnswers={selectedAnswers}
              />
            )}
            {questionPart &&
              !isPendingQuestion &&
              (hasSubmittedQuestionAnswers ? (
                <CompletedQuestionCard questions={questionPart.questions} />
              ) : (
                <div className="question-card__history" role="status">
                  {t("此题卡当前不等待答题。")}
                </div>
              ))}
          </article>
        );
      })}
      {showPendingMessage && pendingMessage && (
        <article
          aria-label={t("正在发送的消息")}
          className="digital-human-message digital-human-message--user digital-human-message--pending"
        >
          <div className="digital-human-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{pendingMessage}</ReactMarkdown>
          </div>
        </article>
      )}
      {(streamedAssistantText || visibleStreamedChart || streamedPlaceCards) && (
        <article
          aria-label={t("助手回答")}
          className="digital-human-message digital-human-message--assistant digital-human-message--streaming"
        >
          <div className="digital-human-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedAssistantText}</ReactMarkdown>
          </div>
          {visibleStreamedChart && <KlineChart chart={visibleStreamedChart} />}
          {streamedPlaceCards && <PlaceCards data={streamedPlaceCards} />}
        </article>
      )}
      {isLoading && (
        <p className="digital-human-message-status" role="status">
          {t("正在加载对话…")}
        </p>
      )}
    </div>
  );
}
