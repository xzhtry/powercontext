import crypto from "node:crypto";
import {
  Schema,
  SeekdbAdminClient,
  SeekdbClient,
  FulltextIndexConfig,
  VectorIndexConfig,
} from "seekdb";
import { config, seekdbArgs } from "./config.mjs";

const now = () => Date.now();
const shortId = () => crypto.randomBytes(8).toString("hex");
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

const REGISTRY_TABLE = "stepkb_collections";
const DOCS_TABLE = "stepkb_docs";

function normalizeNumber(value) {
  return value == null ? value : Number(value);
}

function normalizeKb(row) {
  if (!row) return null;
  return {
    id: row.id,
    name: row.name,
    description: row.description || "",
    collectionName: row.collectionName ?? row.collection_name,
    createdAt: normalizeNumber(row.createdAt ?? row.created_at),
    updatedAt: normalizeNumber(row.updatedAt ?? row.updated_at),
    docCount: normalizeNumber(row.docCount ?? row.doc_count ?? 0),
    chunkCount: normalizeNumber(row.chunkCount ?? row.chunk_count ?? 0),
    dimension: normalizeNumber(row.dimension ?? config.model.dimension),
    embeddingModel: row.embeddingModel ?? row.embedding_model ?? config.model.id,
  };
}

function normalizeDoc(row) {
  if (!row) return null;
  return {
    id: row.id,
    kbId: row.kb_id ?? row.kbId,
    title: row.title,
    source: row.source || "",
    charCount: normalizeNumber(row.char_count ?? row.charCount ?? 0),
    chunkCount: normalizeNumber(row.chunk_count ?? row.chunkCount ?? 0),
    contentHash: row.content_hash ?? row.contentHash ?? null,
    createdAt: normalizeNumber(row.created_at ?? row.createdAt),
  };
}

export class KnowledgeDatabase {
  constructor({ log = console.log } = {}) {
    this.log = log;
    this.client = null;
    this.admin = null;
    this.collections = new Map();
    this.collectionTables = new Map();
    this.hybridTrace = null;
    this.startedAt = now();
    this.version = null;
  }

  async connect() {
    if (config.seekdb.mode === "embedded") {
      this.log(`[seekdb] embedded mode: ${config.seekdb.path}`);
    } else {
      this.log(
        `[seekdb] connecting to ${config.seekdb.host}:${config.seekdb.port}/${config.seekdb.database}`,
      );
    }

    let lastError;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        this.admin = new SeekdbAdminClient(seekdbArgs({ admin: true }));
        const databases = await this.admin.listDatabases();
        const names = databases.map((db) => db.name);
        if (!names.includes(config.seekdb.database)) {
          this.log(`[seekdb] creating database ${config.seekdb.database}`);
          await this.admin.createDatabase(config.seekdb.database);
        }
        await this.admin.close();
        this.admin = null;

        this.client = new SeekdbClient(seekdbArgs());
        const versionRows = await this.client.execute("SELECT VERSION() AS version");
        this.version = versionRows?.[0]?.version || "seekdb";
        this.log(`[seekdb] connected: ${this.version}`);

        await this.createRegistry();
        return this;
      } catch (error) {
        lastError = error;
        try {
          await this.admin?.close();
        } catch {
          /* ignore */
        }
        this.admin = null;
        if (attempt < 3) {
          this.log(`[seekdb] connect attempt ${attempt} failed: ${error.message}; retrying...`);
          await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
        }
      }
    }
    throw new Error(
      `Unable to connect to seekdb (${config.seekdb.mode} mode). ` +
        `Start a seekdb server and check SEEKDB_HOST/SEEKDB_PORT. Cause: ${lastError?.message}`,
    );
  }

  async createRegistry() {
    await this.client.execute(`
      CREATE TABLE IF NOT EXISTS ${REGISTRY_TABLE} (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        description VARCHAR(1000) NOT NULL DEFAULT '',
        collection_name VARCHAR(128) NOT NULL,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        doc_count INT NOT NULL DEFAULT 0,
        chunk_count INT NOT NULL DEFAULT 0,
        dimension INT NOT NULL DEFAULT ${config.model.dimension},
        embedding_model VARCHAR(128) NOT NULL DEFAULT '${config.model.id}'
      ) DEFAULT CHARSET = utf8mb4
    `);

    await this.client.execute(`
      CREATE TABLE IF NOT EXISTS ${DOCS_TABLE} (
        id VARCHAR(64) PRIMARY KEY,
        kb_id VARCHAR(64) NOT NULL,
        title VARCHAR(500) NOT NULL,
        source VARCHAR(500) NOT NULL DEFAULT '',
        char_count INT NOT NULL DEFAULT 0,
        chunk_count INT NOT NULL DEFAULT 0,
        content_hash CHAR(64) NULL,
        created_at BIGINT NOT NULL,
        KEY idx_stepkb_docs_kb (kb_id)
      ) DEFAULT CHARSET = utf8mb4
    `);

    const rows = await this.client.execute(`SELECT id FROM ${REGISTRY_TABLE} LIMIT 1`);
    if (!rows || rows.length === 0) {
      await this.createKb({
        name: "产品与技术知识库",
        description: "示例知识库：端侧模型、seekdb 混合检索与向量数据库工程笔记。",
      });
    }
  }

  async close() {
    try {
      await this.client?.close();
    } finally {
      this.client = null;
    }
  }

  async listKbs() {
    const rows = await this.client.execute(
      `SELECT id, name, description, collection_name AS collectionName,
              created_at AS createdAt, updated_at AS updatedAt,
              doc_count AS docCount, chunk_count AS chunkCount,
              dimension, embedding_model AS embeddingModel
         FROM ${REGISTRY_TABLE}
        ORDER BY created_at ASC`,
    );
    return (rows || []).map(normalizeKb);
  }

  async getKb(id) {
    const rows = await this.client.execute(
      `SELECT id, name, description, collection_name AS collectionName,
              created_at AS createdAt, updated_at AS updatedAt,
              doc_count AS docCount, chunk_count AS chunkCount,
              dimension, embedding_model AS embeddingModel
         FROM ${REGISTRY_TABLE}
        WHERE id = ? LIMIT 1`,
      [id],
    );
    return normalizeKb(rows?.[0]);
  }

  async createKb({ name, description = "" }) {
    const cleanName = String(name || "").trim();
    if (cleanName.length < 1 || cleanName.length > 80) {
      throw Object.assign(new Error("知识库名称长度需为 1–80 个字符"), { status: 400 });
    }
    if (String(description).length > 500) {
      throw Object.assign(new Error("知识库描述不能超过 500 个字符"), { status: 400 });
    }

    const id = shortId();
    const collectionName = `kb_${id}`;
    const dimension = config.model.dimension;
    const schema = new Schema({
      fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
      vectorIndex: new VectorIndexConfig({
        hnsw: {
          dimension,
          distance: "cosine",
          type: "hnsw",
          m: 16,
          ef_construction: 200,
        },
        embeddingFunction: null,
      }),
    });

    await this.client.createCollection({ name: collectionName, schema });
    try {
      const ts = now();
      await this.client.execute(
        `INSERT INTO ${REGISTRY_TABLE}
          (id, name, description, collection_name, created_at, updated_at,
           doc_count, chunk_count, dimension, embedding_model)
         VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)`,
        [id, cleanName, String(description || ""), collectionName, ts, ts, dimension, config.model.id],
      );
    } catch (error) {
      await this.client.deleteCollection(collectionName).catch(() => {});
      throw error;
    }
    return this.getKb(id);
  }

  async deleteKb(id) {
    const kb = await this.getKb(id);
    if (!kb) throw Object.assign(new Error("知识库不存在"), { status: 404 });
    await this.client.deleteCollection(kb.collectionName).catch((error) => {
      if (!/not found|does not exist|unknown/i.test(error.message)) throw error;
    });
    await this.client.execute(`DELETE FROM ${DOCS_TABLE} WHERE kb_id = ?`, [id]);
    await this.client.execute(`DELETE FROM ${REGISTRY_TABLE} WHERE id = ?`, [id]);
    this.collections.delete(kb.collectionName);
    return { id };
  }

  async collectionFor(kb) {
    let collection = this.collections.get(kb.collectionName);
    if (!collection) {
      collection = await this.client.getCollection({
        name: kb.collectionName,
        embeddingFunction: null,
      });
      this.collections.set(kb.collectionName, collection);
    }
    return collection;
  }

  async listDocs(kbId) {
    const rows = await this.client.execute(
      `SELECT id, kb_id, title, source, char_count, chunk_count, content_hash, created_at
         FROM ${DOCS_TABLE} WHERE kb_id = ? ORDER BY created_at DESC`,
      [kbId],
    );
    return (rows || []).map(normalizeDoc);
  }

  async getDoc(kbId, docId) {
    const rows = await this.client.execute(
      `SELECT id, kb_id, title, source, char_count, chunk_count, content_hash, created_at
         FROM ${DOCS_TABLE} WHERE kb_id = ? AND id = ? LIMIT 1`,
      [kbId, docId],
    );
    return normalizeDoc(rows?.[0]);
  }

  async refreshIndex(collection) {
    const started = performance.now();
    await collection.refresh_index();
    return performance.now() - started;
  }

  async ingest({ kbId, title, source = "", text, chunks, contentHash = null }) {
    const kb = await this.getKb(kbId);
    if (!kb) throw Object.assign(new Error("知识库不存在"), { status: 404 });

    const cleanTitle = String(title || "").trim();
    const cleanText = String(text || "").trim();
    if (!cleanTitle) throw Object.assign(new Error("文档标题不能为空"), { status: 400 });
    if (!cleanText) throw Object.assign(new Error("文档内容不能为空"), { status: 400 });
    if (!Array.isArray(chunks) || chunks.length === 0) {
      throw Object.assign(new Error("缺少文本分块"), { status: 400 });
    }
    if (chunks.length > 300) {
      throw Object.assign(new Error("单次导入最多 300 个分块"), { status: 400 });
    }
    if (chunks.some((chunk) => !chunk || !Array.isArray(chunk.embedding))) {
      throw Object.assign(new Error("分块必须包含 embedding 数组"), { status: 400 });
    }
    if (
      chunks.some(
        (chunk) =>
          chunk.embedding.length !== config.model.dimension ||
          chunk.embedding.some((value) => !Number.isFinite(value)),
      )
    ) {
      throw Object.assign(
        new Error(`embedding 维度必须为 ${config.model.dimension}，且全部为有限数值`),
        { status: 400 },
      );
    }

    const hash = contentHash || sha256(cleanText);
    const duplicateRows = await this.client.execute(
      `SELECT id, title FROM ${DOCS_TABLE} WHERE kb_id = ? AND content_hash = ? LIMIT 1`,
      [kbId, hash],
    );
    if (duplicateRows && duplicateRows.length > 0) {
      return {
        duplicate: true,
        docId: duplicateRows[0].id,
        title: duplicateRows[0].title,
        message: "相同内容的文档已存在，已跳过重复导入",
      };
    }

    const docId = `doc_${shortId()}`;
    const collection = await this.collectionFor(kb);
    const ts = now();
    const effectiveSource = String(source || cleanTitle).slice(0, 500);
    const ids = [];
    const documents = [];
    const embeddings = [];
    const metadatas = [];

    chunks.forEach((chunk, index) => {
      const chunkText = String(chunk.text || "").trim();
      if (!chunkText) {
        throw Object.assign(new Error(`第 ${index + 1} 个分块内容为空`), { status: 400 });
      }
      // Normalize server-side as a guard; the actual vectors are computed in the browser.
      const vector = normalizeVector(chunk.embedding);
      ids.push(`c_${docId}_${String(index).padStart(3, "0")}`);
      documents.push(chunkText);
      embeddings.push(vector);
      metadatas.push({
        docId,
        kbId,
        title: cleanTitle.slice(0, 500),
        source: effectiveSource,
        chunkIndex: index,
        chunkCount: chunks.length,
        charCount: chunkText.length,
        ingestedAt: ts,
      });
    });

    const writeStarted = performance.now();
    let refreshedMs = null;
    try {
      const batchSize = 64;
      for (let i = 0; i < ids.length; i += batchSize) {
        const end = Math.min(i + batchSize, ids.length);
        await collection.add({
          ids: ids.slice(i, end),
          documents: documents.slice(i, end),
          embeddings: embeddings.slice(i, end),
          metadatas: metadatas.slice(i, end),
        });
      }
      refreshedMs = await this.refreshIndex(collection);
      const registryStarted = performance.now();
      await this.client.execute(
        `INSERT INTO ${DOCS_TABLE}
          (id, kb_id, title, source, char_count, chunk_count, content_hash, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [docId, kbId, cleanTitle.slice(0, 500), effectiveSource, cleanText.length, chunks.length, hash, ts],
      );
      await this.client.execute(
        `UPDATE ${REGISTRY_TABLE}
            SET doc_count = doc_count + 1,
                chunk_count = chunk_count + ?,
                updated_at = ?
          WHERE id = ?`,
        [chunks.length, ts, kbId],
      );
      const registryMs = performance.now() - registryStarted;
      const totalMs = performance.now() - writeStarted;
      const refreshMs = refreshedMs;

      this.log(
        `[ingest] ${kbId} ${docId} "${cleanTitle}" chunks=${chunks.length} ` +
          `write=${totalMs.toFixed(1)}ms refresh=${refreshMs.toFixed(1)}ms registry=${registryMs.toFixed(1)}ms`,
      );
      return {
        duplicate: false,
        docId,
        title: cleanTitle,
        chunkCount: chunks.length,
        writeMs: round(totalMs),
        refreshMs: round(refreshMs),
        registryMs: round(registryMs),
        collectionCount: await collection.count(),
      };
    } catch (error) {
      // Do not leave half-inserted chunks behind.
      await collection.delete({ where: { docId } }).catch(() => {});
      throw error;
    }
  }

  /**
   * Import a batch of already-embedded documents, coalescing index refreshes.
   * The browser computes every vector; this method only persists and refreshes.
   */
  async ingestBatch({ kbId, documents }) {
    const kb = await this.getKb(kbId);
    if (!kb) throw Object.assign(new Error("知识库不存在"), { status: 404 });
    if (!Array.isArray(documents) || documents.length === 0) {
      throw Object.assign(new Error("缺少待导入文档"), { status: 400 });
    }
    if (documents.length > 50) {
      throw Object.assign(new Error("单批最多 50 篇文档"), { status: 400 });
    }
    const collection = await this.collectionFor(kb);
    const prepared = [];
    const seen = new Set();
    let duplicateCount = 0;
    const started = performance.now();

    for (const raw of documents) {
      const title = String(raw?.title || "").trim();
      const text = String(raw?.text || "").trim();
      const chunks = raw?.chunks;
      if (!title || !text) {
        throw Object.assign(new Error("每篇文档都必须有标题和正文"), { status: 400 });
      }
      if (!Array.isArray(chunks) || chunks.length === 0 || chunks.length > 300) {
        throw Object.assign(
          new Error(`文档《${title}》必须包含 1–300 个分块`),
          { status: 400 },
        );
      }
      if (
        chunks.some(
          (chunk) =>
            !chunk ||
            !Array.isArray(chunk.embedding) ||
            chunk.embedding.length !== config.model.dimension ||
            chunk.embedding.some((value) => !Number.isFinite(value)),
        )
      ) {
        throw Object.assign(
          new Error(`文档《${title}》的 embedding 维度必须为 ${config.model.dimension}`),
          { status: 400 },
        );
      }
      const hash = raw.contentHash || sha256(text);
      if (seen.has(hash)) {
        duplicateCount += 1;
        continue;
      }
      seen.add(hash);
      const existing = await this.client.execute(
        `SELECT id FROM ${DOCS_TABLE} WHERE kb_id = ? AND content_hash = ? LIMIT 1`,
        [kbId, hash],
      );
      if (existing && existing.length > 0) {
        duplicateCount += 1;
        continue;
      }
      prepared.push({
        docId: `doc_${shortId()}`,
        title: title.slice(0, 500),
        source: String(raw.source || title).slice(0, 500),
        text,
        chunks,
        hash,
        ts: now(),
      });
    }

    if (prepared.length === 0) {
      return {
        duplicate: true,
        imported: 0,
        duplicateCount,
        message: "这批文档均已存在，未重复写入",
      };
    }

    const ids = [];
    const documentsText = [];
    const embeddings = [];
    const metadatas = [];
    for (const doc of prepared) {
      doc.chunks.forEach((chunk, index) => {
        const chunkText = String(chunk.text || "").trim();
        if (!chunkText) {
          throw Object.assign(
            new Error(`文档《${doc.title}》第 ${index + 1} 个分块为空`),
            { status: 400 },
          );
        }
        ids.push(`c_${doc.docId}_${String(index).padStart(3, "0")}`);
        documentsText.push(chunkText);
        embeddings.push(normalizeVector(chunk.embedding));
        metadatas.push({
          docId: doc.docId,
          kbId,
          title: doc.title,
          source: doc.source,
          chunkIndex: index,
          chunkCount: doc.chunks.length,
          charCount: chunkText.length,
          ingestedAt: doc.ts,
        });
      });
    }

    try {
      const batchSize = 64;
      for (let i = 0; i < ids.length; i += batchSize) {
        const end = Math.min(i + batchSize, ids.length);
        await collection.add({
          ids: ids.slice(i, end),
          documents: documentsText.slice(i, end),
          embeddings: embeddings.slice(i, end),
          metadatas: metadatas.slice(i, end),
        });
      }
      const refreshMs = await this.refreshIndex(collection);
      const totalChunks = ids.length;
      for (const doc of prepared) {
        await this.client.execute(
          `INSERT INTO ${DOCS_TABLE}
            (id, kb_id, title, source, char_count, chunk_count, content_hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            doc.docId,
            kbId,
            doc.title,
            doc.source,
            doc.text.length,
            doc.chunks.length,
            doc.hash,
            doc.ts,
          ],
        );
      }
      await this.client.execute(
        `UPDATE ${REGISTRY_TABLE}
            SET doc_count = doc_count + ?,
                chunk_count = chunk_count + ?,
                updated_at = ?
          WHERE id = ?`,
        [prepared.length, totalChunks, now(), kbId],
      );
      const writeMs = performance.now() - started;
      this.log(
        `[ingest-batch] ${kbId} docs=${prepared.length} chunks=${totalChunks} ` +
          `write=${writeMs.toFixed(1)}ms refresh=${refreshMs.toFixed(1)}ms duplicates=${duplicateCount}`,
      );
      return {
        duplicate: false,
        imported: prepared.length,
        duplicateCount,
        chunkCount: totalChunks,
        docs: prepared.map((doc) => ({
          docId: doc.docId,
          title: doc.title,
          chunkCount: doc.chunks.length,
        })),
        writeMs: round(writeMs),
        refreshMs: round(refreshMs),
        collectionCount: await collection.count(),
      };
    } catch (error) {
      for (const doc of prepared) {
        await collection.delete({ where: { docId: doc.docId } }).catch(() => {});
      }
      throw error;
    }
  }

  async deleteDoc(kbId, docId) {
    const kb = await this.getKb(kbId);
    if (!kb) throw Object.assign(new Error("知识库不存在"), { status: 404 });
    const doc = await this.getDoc(kbId, docId);
    if (!doc) throw Object.assign(new Error("文档不存在"), { status: 404 });
    const collection = await this.collectionFor(kb);
    const started = performance.now();
    await collection.delete({ where: { docId } });
    const refreshMs = await this.refreshIndex(collection);
    await this.client.execute(`DELETE FROM ${DOCS_TABLE} WHERE kb_id = ? AND id = ?`, [kbId, docId]);
    await this.client.execute(
      `UPDATE ${REGISTRY_TABLE}
          SET doc_count = GREATEST(doc_count - 1, 0),
              chunk_count = GREATEST(chunk_count - ?, 0),
              updated_at = ?
        WHERE id = ?`,
      [doc.chunkCount, now(), kbId],
    );
    return {
      docId,
      deleteMs: round(performance.now() - started),
      refreshMs: round(refreshMs),
    };
  }

  /**
   * Hybrid retrieval is executed in one seekdb call:
   * DBMS_HYBRID_SEARCH.GET_SQL + the generated SQL, with RRF ranking.
   * The Node layer never receives two ranked lists and merges them itself.
   */
  async search({
    kbId,
    query,
    embedding,
    topK = 8,
    mode = "hybrid",
    rankWindowSize = 60,
    rankConstant = 60,
  }) {
    const kb = await this.getKb(kbId);
    if (!kb) throw Object.assign(new Error("知识库不存在"), { status: 404 });
    if (!query || !String(query).trim()) {
      throw Object.assign(new Error("查询不能为空"), { status: 400 });
    }
    if (
      !Array.isArray(embedding) ||
      embedding.length !== config.model.dimension ||
      embedding.some((value) => !Number.isFinite(value))
    ) {
      throw Object.assign(
        new Error(`查询向量维度必须为 ${config.model.dimension}`),
        { status: 400 },
      );
    }
    const collection = await this.collectionFor(kb);
    const queryVector = normalizeVector(embedding);
    const cleanQuery = String(query).trim().slice(0, 500);
    const ftsQuery = buildFtsQuery(cleanQuery);
    const candidateK = Math.max(topK * 4, 24);
    const started = performance.now();
    this.hybridTrace = null;

    let result;
    if (mode === "fts") {
      result = await collection.get({
        whereDocument: ftsQuery ? { $contains: ftsQuery } : undefined,
        limit: topK,
        include: ["documents", "metadatas"],
      });
    } else if (mode === "vector" || !ftsQuery) {
      result = await collection.query({
        queryEmbeddings: queryVector,
        nResults: topK,
        include: ["documents", "metadatas", "distances"],
      });
    } else {
      result = await collection.hybridSearch({
        query: { whereDocument: { $or: tokenConditions(cleanQuery, ftsQuery) } },
        knn: {
          queryEmbeddings: queryVector,
          nResults: candidateK,
        },
        rank: { rrf: { rankWindowSize, rankConstant } },
        nResults: topK,
        include: ["documents", "metadatas", "distances"],
      });
    }
    const dbMs = performance.now() - started;

    if (mode === "hybrid" && ftsQuery) {
      // Evidence only: ask seekdb to render the SQL for the same parameters. The
      // ranked results above already came from the SDK's own in-database hybrid call.
      try {
        await this.captureHybridTrace({
          kb,
          queryString: ftsQuery,
          queryVector,
          candidateK,
          topK,
          rankWindowSize,
          rankConstant,
        });
      } catch (error) {
        this.log(`[trace] unable to render hybrid SQL: ${error.message}`);
      }
    }

    const hits = flattenResult(result, mode).slice(0, topK);
    return {
      hits,
      mode: mode === "hybrid" && !ftsQuery ? "vector-fallback" : mode,
      query: cleanQuery,
      ftsQuery,
      topK,
      dbMs: round(dbMs),
      totalMs: round(performance.now() - started),
      count: hits.length,
      seekdb: {
        engine: this.version,
        api: mode === "hybrid" && ftsQuery ? "collection.hybridSearch" : mode === "fts" ? "collection.get" : "collection.query",
        rank: mode === "hybrid" && ftsQuery ? "RRF" : "none",
        rankWindowSize,
        rankConstant,
        fts: Boolean(ftsQuery),
        executedInDatabase: true,
      },
      hybridTrace: this.hybridTrace
        ? {
            generatedSql: this.hybridTrace.generatedSql,
            searchParm: this.hybridTrace.searchParm,
            generatedAt: this.hybridTrace.generatedAt,
            note: this.hybridTrace.note,
          }
        : null,
    };
  }

  async captureHybridTrace({ kb, queryString, queryVector, candidateK, topK, rankWindowSize, rankConstant }) {
    let tableName = this.collectionTables.get(kb.collectionName);
    if (!tableName) {
      const rows = await this.client.execute(
        "SELECT collection_id FROM sdk_collections WHERE collection_name = ? LIMIT 1",
        [kb.collectionName],
      );
      const collectionId = rows?.[0]?.collection_id;
      if (!collectionId) return;
      tableName = `c$v2$${collectionId}`;
      this.collectionTables.set(kb.collectionName, tableName);
    }
    const searchParm = {
      query: { query_string: { fields: ["document"], query: queryString } },
      knn: { field: "embedding", k: candidateK, query_vector: queryVector },
      rank: { rrf: { rank_window_size: rankWindowSize, rank_constant: rankConstant } },
      size: topK,
    };
    await this.client.execute("SET @stepkb_trace_parm = ?", [JSON.stringify(searchParm)]);
    const rows = await this.client.execute(
      "SELECT DBMS_HYBRID_SEARCH.GET_SQL(?, @stepkb_trace_parm) AS query_sql FROM dual",
      [tableName],
    );
    const generatedSql = rows?.[0]?.query_sql || null;
    if (generatedSql) {
      this.hybridTrace = {
        generatedSql,
        searchParm,
        generatedAt: now(),
        note:
          "Generated by seekdb DBMS_HYBRID_SEARCH.GET_SQL; FTS MATCH ... AGAINST and cosine_distance are joined and RRF-fused inside one SQL statement.",
      };
    }
  }

  async stats() {
    const kbCount = await this.client.execute(`SELECT COUNT(*) AS cnt FROM ${REGISTRY_TABLE}`);
    const docCount = await this.client.execute(`SELECT COUNT(*) AS cnt FROM ${DOCS_TABLE}`);
    const chunkCount = await this.client.execute(
      `SELECT COALESCE(SUM(chunk_count), 0) AS cnt FROM ${REGISTRY_TABLE}`,
    );
    return {
      kbCount: normalizeNumber(kbCount?.[0]?.cnt || 0),
      docCount: normalizeNumber(docCount?.[0]?.cnt || 0),
      chunkCount: normalizeNumber(chunkCount?.[0]?.cnt || 0),
    };
  }
}

function normalizeVector(vector) {
  let sum = 0;
  for (const value of vector) sum += value * value;
  const norm = Math.sqrt(sum);
  if (!Number.isFinite(norm) || norm === 0) {
    throw Object.assign(new Error("embedding 不能为零向量"), { status: 400 });
  }
  return vector.map((value) => Number((value / norm).toFixed(8)));
}

const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;
const STOPWORDS = new Set([
  "的", "了", "是", "和", "与", "及", "在", "有", "为", "如何", "怎么", "什么", "是什么",
  "为什么", "哪些", "这个", "那个", "应该", "是否", "可以", "需要",
  "the", "a", "an", "is", "are", "was", "were", "how", "what", "which", "and", "or", "of", "to", "in",
  "on", "for", "with", "does", "do", "did", "can", "could", "should", "would", "please",
]);

/**
 * Turn a natural-language query into safe query_string terms.
 * Chinese text without spaces stays as one term (the ik analyzer tokenizes it);
 * English is split into terms and OR-ed so one missing word does not kill the FTS branch.
 */
export function buildFtsQuery(query) {
  const cleaned = String(query || "")
    .normalize("NFKC")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);
  if (!cleaned) return "";
  const parts = cleaned.split(" ").filter((part) => part && !STOPWORDS.has(part.toLowerCase()));
  const terms = [];
  for (const part of parts) {
    if (CJK.test(part)) {
      // Keep CJK phrases intact; the IK analyzer produces meaningful tokens.
      if (part.length >= 2) terms.push(part);
    } else if (part.length >= 2) {
      terms.push(part);
    }
  }
  return [...new Set(terms)].slice(0, 8).join(" OR ");
}

function tokenConditions(query, ftsQuery) {
  const rawParts = String(query || "")
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((part) => part && part.length >= 2 && !STOPWORDS.has(part.toLowerCase()))
    .slice(0, 8);
  if (rawParts.length > 1) {
    return rawParts.map((part) => ({ $contains: part }));
  }
  // A CJK phrase has no spaces: hand the whole normalized phrase to the DB analyzer.
  return [{ $contains: ftsQuery || String(query).slice(0, 100) }];
}

function flattenEntries(groups, field) {
  const first = Array.isArray(groups?.[field]?.[0])
    ? groups[field][0]
    : Array.isArray(groups?.[field])
      ? groups[field]
      : [];
  return first;
}

function flattenResult(result, mode) {
  if (!result) return [];
  const ids = flattenEntries(result, "ids");
  const documents = flattenEntries(result, "documents");
  const metadatas = flattenEntries(result, "metadatas");
  const distances = flattenEntries(result, "distances");
  return ids.map((id, index) => {
    const meta = metadatas[index] || {};
    const distance = distances[index];
    return {
      id,
      rank: index + 1,
      docId: meta.docId || null,
      title: meta.title || "未命名文档",
      source: meta.source || "",
      chunkIndex: Number(meta.chunkIndex ?? 0),
      chunkCount: Number(meta.chunkCount ?? 1),
      text: documents[index] || "",
      score: distance == null ? null : Number(distance),
      scoreLabel: mode === "hybrid" ? "RRF" : "distance",
      metadata: meta,
    };
  });
}

function round(value) {
  return Math.round(value * 10) / 10;
}
