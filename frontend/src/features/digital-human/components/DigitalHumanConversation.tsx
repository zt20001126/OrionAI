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
  PlaceCard,
  RouteResult,
} from "../../conversations/conversationApi";
import { CompletedQuestionCard, QuestionAnswerCard } from "../../conversations/QuestionAnswerCards";
import { QuestionWizard } from "../../conversations/QuestionWizard";
import { PlatformIcon } from "../../platform/PlatformIcon";

/** 显示商家图片，缺失或加载失败时呈现店铺图标；输入：图片 URL 与商家名；输出：带可访问名称的图片区域；调用方：PlaceCards。 */
function PlaceCardImage({ imageUrl, name }: { imageUrl: string | null; name: string }) {
  const [hasError, setHasError] = useState(false);
  if (!imageUrl || hasError) {
    return (
      <span
        aria-label={`${name}商家图片`}
        className="digital-human-place-card__image-fallback"
        role="img"
      >
        <PlatformIcon name="store" size={30} />
      </span>
    );
  }
  return (
    <img
      alt={`${name}商家图片`}
      className="digital-human-place-card__image"
      loading="lazy"
      onError={() => setHasError(true)}
      src={imageUrl}
    />
  );
}

/** 按米数格式化周边商家距离；输入：高德返回的米数；输出：米或公里文本；调用方：PlaceCards。 */
function formatPlaceDistance(distanceMeters: number): string {
  if (distanceMeters >= 1000) {
    return `约 ${Number((distanceMeters / 1000).toFixed(1))} 公里`;
  }
  return `约 ${Math.round(distanceMeters)} 米`;
}

/** 以毛玻璃三栏卡片展示周边商家；输入：周边搜索结果；输出：图片、资料、评分与地图操作；调用方：数字人历史消息与流式消息。 */
function PlaceCards({
  data,
  onPlanRoute,
  planning,
}: {
  data: PlaceCardsPayload;
  onPlanRoute?: (place: PlaceCard) => void;
  planning?: boolean;
}) {
  return (
    <section aria-label={data.title} className="digital-human-place-cards">
      <div className="digital-human-place-cards__list">
        {data.places.map((place) => {
          const mapKeyword = encodeURIComponent(`${place.name} ${place.address}`);
          return (
            <article className="digital-human-place-card" key={place.id}>
              <PlaceCardImage imageUrl={place.image_url} name={place.name} />
              <div className="digital-human-place-card__content">
                <strong className="digital-human-place-card__name">{place.name}</strong>
                <p className="digital-human-place-card__address">
                  <PlatformIcon name="location" size={17} />
                  <span>{place.address}</span>
                </p>
                <div className="digital-human-place-card__details">
                  <span>{formatPlaceDistance(place.distance)}</span>
                  {place.tel ? (
                    <a href={`tel:${place.tel}`}>
                      <PlatformIcon name="phone" size={17} />
                      <span>{place.tel}</span>
                    </a>
                  ) : (
                    <span>暂无电话</span>
                  )}
                  {place.business_hours && (
                    <span>
                      <PlatformIcon name="store" size={17} />
                      <span>营业 {place.business_hours}</span>
                    </span>
                  )}
                </div>
              </div>
              <aside className="digital-human-place-card__actions">
                {place.rating !== null && (
                  <span
                    aria-label={`评分 ${place.rating.toFixed(1)}`}
                    className="digital-human-place-card__rating"
                    role="img"
                  >
                    <span aria-hidden="true">★</span> {place.rating.toFixed(1)}
                  </span>
                )}
                <div className="digital-human-route-actions">
                  <button
                    type="button"
                    className="digital-human-route-button"
                    disabled={planning || !place.location}
                    onClick={() => onPlanRoute?.(place)}
                    title={!place.location ? "此历史商家缺少坐标，请重新搜索" : undefined}
                  >
                    <PlatformIcon name="send" size={18} />
                    {planning ? "正在规划路线" : "路线规划"}
                  </button>
                  <a
                    aria-label={`在高德地图中查看${place.name}`}
                    className="digital-human-place-card__map-button"
                    href={`https://uri.amap.com/search?keyword=${mapKeyword}&view=map`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <PlatformIcon name="location" size={18} />
                    <span>查看位置</span>
                  </a>
                </div>
              </aside>
            </article>
          );
        })}
      </div>
    </section>
  );
}

/** 按会话和消息标识加载路线图片；输出地图或不可用提示；调用方：路线卡片。 */
function WalkingRouteMap({
  conversationId,
  messageId,
}: {
  conversationId: string;
  messageId: string;
}) {
  const [isUnavailable, setIsUnavailable] = useState(false);
  return (
    <figure className={`digital-human-route-map${isUnavailable ? " is-unavailable" : ""}`}>
      {!isUnavailable && (
        <img
          alt="步行路线地图"
          loading="lazy"
          onError={() => setIsUnavailable(true)}
          src={`/api/conversations/${conversationId}/messages/${messageId}/static-map`}
        />
      )}
      {isUnavailable && <figcaption role="status">路线地图暂时无法显示。</figcaption>}
    </figure>
  );
}

/** 展示步行路线、地图和导航链接；输入路线及消息标识；调用方：数字人会话消息列表。 */
function WalkingRouteCard({
  route,
  conversationId,
  messageId,
}: {
  route: RouteResult;
  conversationId: string;
  messageId: string;
}) {
  const params = new URLSearchParams({
    from: `${route.origin.location},${route.origin.name}`,
    to: `${route.destination.location},${route.destination.name}`,
    mode: "walk",
    src: "OrionAI",
    callnative: "0",
  });
  const map = new URLSearchParams({
    keyword: route.destination.name,
    center: route.destination.location,
    view: "map",
  });
  return (
    <section className="digital-human-walking-route" aria-label="步行路线">
      <h3>步行路线</h3>
      <p>
        <strong>
          {route.distance_m >= 1000
            ? `${(route.distance_m / 1000).toFixed(2)} 公里`
            : `${route.distance_m} 米`}
        </strong>{" "}
        · 约 {Math.max(1, Math.round(route.duration_s / 60))} 分钟
      </p>
      <WalkingRouteMap conversationId={conversationId} messageId={messageId} />
      <ol>
        <li>从{route.origin.name}出发</li>
        {route.steps.map((step, index) => (
          <li key={index}>{step.instruction}</li>
        ))}
        <li>到达 {route.destination.name}</li>
      </ol>
      <div className="digital-human-route-actions">
        <a
          className="digital-human-route-button"
          href={`https://uri.amap.com/search?${map}`}
          target="_blank"
          rel="noreferrer"
        >
          <PlatformIcon name="location" size={20} />
          查看位置
        </a>
        <a
          className="digital-human-place-card__map-button"
          href={`https://uri.amap.com/navigation?${params}`}
          target="_blank"
          rel="noreferrer"
        >
          <PlatformIcon name="send" size={20} />
          开始导航
        </a>
      </div>
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
  onPlanRoute?: (place: PlaceCard) => void;
  isPlanningRoute?: boolean;
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
  onPlanRoute,
  isPlanningRoute,
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
        const routeResult = message.content.parts.find((part) => part.type === "route_result");
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
          !routeResult &&
          !questionPart &&
          !questionAnswersPart
        )
          return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}${questionPart ? " digital-human-message--question" : ""}${questionAnswersPart ? " digital-human-message--question-answers" : ""}${placeCards ? " digital-human-message--places" : ""}`}
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
            {placeCards?.type === "place_cards" && (
              <PlaceCards
                data={placeCards.data}
                onPlanRoute={onPlanRoute}
                planning={isPlanningRoute}
              />
            )}
            {routeResult?.type === "route_result" && (
              <WalkingRouteCard
                conversationId={message.conversation_id}
                messageId={message.id}
                route={routeResult.data}
              />
            )}
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
          className={`digital-human-message digital-human-message--assistant digital-human-message--streaming${streamedPlaceCards ? " digital-human-message--places" : ""}`}
        >
          <div className="digital-human-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedAssistantText}</ReactMarkdown>
          </div>
          {visibleStreamedChart && <KlineChart chart={visibleStreamedChart} />}
          {streamedPlaceCards && (
            <PlaceCards
              data={streamedPlaceCards}
              onPlanRoute={onPlanRoute}
              planning={isPlanningRoute}
            />
          )}
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
