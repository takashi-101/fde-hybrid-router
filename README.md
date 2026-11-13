# FDE Hybrid Router（信頼境界・DB連携・Human-in-the-Loop 振り分け基盤）

クラウド型LLMと閉域ローカルLLMを**データ機密性・セキュリティ境界で自動振り分け**し、DB連携（SQLite）・プロンプトインジェクション検知・低確信度案件の人間レビュー（Human-in-the-Loop）までを一気通貫で実装したリファレンス実装です。

## 1. 解決する現場の課題と設計思想
* **外部通信に伴う攻撃・漏えいリスクの遮断**：クラウド型LLMは「入力→外部処理→出力」という通信経路を持つため、情報漏えいやプロンプトインジェクションの起点になり得る。
* **信頼境界（Trust Boundary）による二層ルーティング**：
  * **公開・非機密情報（`PUBLIC`）**：誰に知られても問題ない情報のみクラウド型LLMルートを許可。
  * **個人情報・内部情報（`INTERNAL_PII`）**：氏名・電話番号・メール・個人番号・金額等を検知した場合、**外部通信を一切行わず**、PIIマスキングを施した上で**閉域ローカルLLMルート**へ強制ルーティング。
* **Prompt Injection Guard（Fail-Closed）**：指示上書き・システムプロンプト抽出等の兆候を検知した場合、クラウド／ローカル双方のLLMへ渡さず `ESCALATED_SECURITY` として人間レビューへ即時隔離。
* **Human-in-the-Loop（Abstain設計）**：確信度が閾値（デフォルト `0.80`）未満、または高リスク案件は自動回答せず、DB内の `human_review_queue` テーブルへ振り分ける。

## 2. 構成
* `src/hybrid_router/guard.py`：機密区分判定・PIIマスキング・プロンプトインジェクション検知
* `src/hybrid_router/db.py`：DB連携（`inquiries` / `routing_results` / `human_review_queue`）
* `src/hybrid_router/router.py`：信頼境界ルーティング＋Human-in-the-Loop振り分け
* `tests/test_hybrid_router.py`：外部流出ゼロ・インジェクション遮断・HITL振り分けの自動検証テスト

## 3. クイックスタート

```bash
# 1. 自動テストの実行
python3 -m unittest discover -s tests -v

# 2. SQLite連携デモの実行
PYTHONPATH=src python3 -m hybrid_router.cli --db /tmp/fde_hybrid_demo.db
```
