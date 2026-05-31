const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak,
  ExternalHyperlink
} = require("docx");

// ── Helpers ──
const ACCENT = "2B579A";
const LIGHT_BG = "F2F5FA";
const border = { style: BorderStyle.SINGLE, size: 1, color: "DDDDDD" };
const borders = { top: border, bottom: border, left: border, right: border };

function sectionTitle(text) {
  return new Paragraph({
    spacing: { before: 360, after: 120 },
    borders: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 4 } },
    children: [new TextRun({ text, font: "SimHei", size: 26, bold: true, color: ACCENT })],
  });
}

function infoLine(label, value) {
  return new Paragraph({
    spacing: { before: 40, after: 40 },
    children: [
      new TextRun({ text: label, font: "SimSun", size: 22, bold: true, color: "444444" }),
      new TextRun({ text: value, font: "SimSun", size: 22, color: "333333" }),
    ],
  });
}

function subTitle(text) {
  return new Paragraph({
    spacing: { before: 200, after: 60 },
    children: [new TextRun({ text, font: "SimHei", size: 23, bold: true, color: "222222" })],
  });
}

function techStack(text) {
  return new Paragraph({
    spacing: { before: 20, after: 80 },
    children: [new TextRun({ text, font: "SimSun", size: 20, italic: true, color: ACCENT })],
  });
}

function bulletItem(text) {
  return new Paragraph({
    spacing: { before: 30, after: 30 },
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text, font: "SimSun", size: 21, color: "333333" })],
  });
}

function linkItem(label, url) {
  return new Paragraph({
    spacing: { before: 20, after: 20 },
    children: [
      new TextRun({ text: label + "：", font: "SimSun", size: 21, bold: true, color: "555555" }),
      new ExternalHyperlink({
        children: [new TextRun({ text: url, font: "SimSun", size: 21, color: "2B579A", style: "Hyperlink" })],
        link: url,
      }),
    ],
  });
}

// ── Personal Info Table ──
const infoTable = () => {
  const labelStyle = { font: "SimHei", size: 22, bold: true, color: "444444" };
  const valueStyle = { font: "SimSun", size: 22, color: "333333" };
  const cell = (label, value, w) =>
    new TableCell({
      width: { size: w, type: WidthType.DXA },
      margins: { top: 40, bottom: 40, left: 60, right: 60 },
      children: [new Paragraph({ children: [new TextRun(labelStyle), new TextRun(value)] })],
    });

  return new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2256, 2256, 2256, 2258],
    rows: [
      new TableRow({
        children: [
          cell({ text: "姓　　名：", ...labelStyle }, "陈宇康", 2256),
          cell({ text: "电　　话：", ...labelStyle }, "18796392267", 2256),
          cell({ text: "学　　校：", ...labelStyle }, "南京林业大学", 2256),
          cell({ text: "专　　业：", ...labelStyle }, "园林", 2258),
        ],
      }),
      new TableRow({
        children: [
          cell({ text: "年　　级：", ...labelStyle }, "大三（2027 年毕业）", 2256),
          cell({ text: "邮　　箱：", ...labelStyle }, "3342096170@qq.com", 2256),
          cell({ text: "绩　　点：", ...labelStyle }, "3.0+/4.0", 2256),
          cell({ text: "证　　书：", ...labelStyle }, "计算机二级", 2258),
        ],
      }),
    ],
  });
};

// ── Build Document ──
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: "SimSun", size: 21 } } },
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1134, right: 1440, bottom: 1134, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "简历 — 陈宇康", font: "SimSun", size: 18, color: "999999" })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "Page ", font: "SimSun", size: 18, color: "999999" }), new TextRun({ children: [PageNumber.CURRENT], font: "SimSun", size: 18, color: "999999" })],
          })],
        }),
      },
      children: [
        // ── Header: Name ──
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 60 },
          children: [new TextRun({ text: "陈宇康", font: "SimHei", size: 36, bold: true, color: "1A1A1A" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "求职意向：AI 产品运营 / AI Agent 开发实习生", font: "SimSun", size: 22, color: ACCENT, bold: true })],
        }),

        // ── Personal Info ──
        sectionTitle("个人信息"),
        infoTable(),

        // ── Project Experience ──
        sectionTitle("项目经验"),

        subTitle("Character Agent — 类人记忆的 AI 角色对话系统"),
        techStack("Python / FastAPI / DeepSeek / SQLite / 无向量纯文本记忆"),
        linkItem("GitHub", "https://github.com/12345789dabai/character-agent"),
        linkItem("在线体验", "http://39.106.182.113:8000"),
        bulletItem("设计并实现了四层记忆系统（L0 核心信念 / L1 重要事实 / L2 一般经历 / L3 日常琐事），完全替代传统向量数据库 + RAG 方案，无需 embedding 和向量检索"),
        bulletItem("引入自述权重优先机制（角色自己说的话权重 3 倍于他人所述），配合情绪强度加权和热度衰减算法，使记忆更接近人类遗忘曲线"),
        bulletItem("设计并实现角色生命周期系统，包含五阶段时间推进（相遇→相伴→成长→沉淀→告别）、梯度阈值和阶段感知 prompt 注入，角色语气随关系发展阶段自然变化"),
        bulletItem("全栈独立开发，集成 DeepSeek 大模型 API，部署至阿里云服务器，配置密码访问保护，适配移动端浏览"),

        subTitle("AI 短剧辅助制作工具"),
        techStack("Python / 多模型 API / 音频合成 / 图像生成"),
        linkItem("GitHub", "https://github.com/12345789dabai/short-drama-tool"),
        bulletItem("集成文本生成、图像生成、音频合成等多模型 API，构建从剧本到成片的端到端 AI 短剧制作管线"),
        bulletItem("采用模块化架构设计，各环节可独立替换服务提供商，灵活适配不同业务场景"),
        bulletItem("支持 Web 端与桌面端双模式运行，覆盖不同创作场景"),

        // ── Skills ──
        sectionTitle("技术能力"),
        bulletItem("编程语言：Python（熟练使用），了解 JavaScript / TypeScript"),
        bulletItem("后端开发：FastAPI 框架，RESTful API 设计与开发，无向量纯文本记忆系统设计"),
        bulletItem("AI 工程：熟练调用 DeepSeek、通义千问等大模型 API，Prompt Engineering 实战经验，AI Agent 记忆系统架构设计"),
        bulletItem("开发工具：Git 版本控制，熟练使用 Claude Code / Codex 等 AI 辅助编程工具，配置与集成 MCP 协议服务"),
        bulletItem("运维部署：Linux 服务器基础操作，阿里云服务器部署，服务端鉴权配置"),
        bulletItem("AI 生态：参与小米百万亿 Token 创造者激励计划（Max 套餐），具备多厂商大模型 API 集成与调用经验"),

        // ── Self Assessment ──
        sectionTitle("自我评价"),
        bulletItem("对 AI 产品与技术有强烈兴趣，具备独立开发和落地完整项目的能力"),
        bulletItem("善于学习新技术，能快速上手各类 AI 工具与 API"),
        bulletItem("了解 AI 短剧和 AI 产品的海外运营工作流，能将技术与应用场景结合思考"),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync("resume.docx", buffer);
  console.log("OK: 简历-陈宇康.docx");
});
