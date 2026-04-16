# SW Maestro Project

SW 마에스트로 최종 프로젝트 제출 저장소입니다.

이 저장소에 팀별 프로젝트를 제출하면, 코치가 GitHub Issue를 통해 피드백을 드립니다.

---

## 제출 전 꼭 읽어주세요

### 팀 폴더 네이밍 규칙

팀 폴더명은 아래 형식을 따라주세요. 팀 번호가 앞에 있어야 정렬이 되어 관리가 편합니다!

```
team{번호}-{팀이름}
```

| 형식 | 예시 | 비고 |
|---|---|---|
| `team{번호}-{팀이름}` | `team1-newscatcher` | 영문 소문자만 사용 |
| | `team15-budgetbuddy` | 공백, 특수문자, 한글 불가 |
| | `team42-studybot` | |

---

## 프로젝트 제출 방법

Git이 처음이어도 괜찮습니다! 아래 단계를 차근차근 따라오세요.

### Step 1. 이 저장소를 Fork 하세요

GitHub 페이지 우측 상단의 **Fork** 버튼을 클릭하면, 자신의 GitHub 계정에 동일한 저장소가 복사됩니다.

> Fork란? 원본 저장소를 내 계정으로 복사하는 것입니다. 원본에 직접 영향을 주지 않으니 안심하세요!

### Step 2. Fork한 저장소를 로컬에 Clone 하세요

```bash
git clone https://github.com/<내-GitHub-아이디>/sw-maestro-project.git
cd sw-maestro-project
```

> `<내-GitHub-아이디>` 부분을 자신의 GitHub 아이디로 바꿔주세요.

### Step 3. 팀 폴더를 만들고 프로젝트를 넣으세요

```bash
# 팀 폴더 생성 (팀 번호와 이름을 자신의 것으로 변경하세요)
mkdir -p projects/team1-myteamname

# 프로젝트 파일 복사
cp -r /path/to/your-project/* projects/team1-myteamname/
```

완료되면 아래와 같은 구조가 됩니다:

```
sw-maestro-project/
└── projects/
    └── team1-myteamname/
        ├── README.md        ← 프로젝트 설명
        ├── backend/         ← 백엔드 코드
        ├── frontend/        ← 프론트엔드 코드
        └── ...
```

> 프로젝트 폴더 안에 **README.md**를 꼭 포함해주세요! 프로젝트 소개, 실행 방법, 기술 스택 등을 적어주시면 피드백에 큰 도움이 됩니다.

### Step 4. Commit & Push 하세요

```bash
git add .
git commit -m "[Team 1] 프로젝트 제출 - myteamname"
git push origin main
```

### Step 5. Pull Request를 만드세요

1. GitHub에서 **자신의 Fork 저장소**로 이동합니다.
2. 상단에 나타나는 **"Contribute"** 버튼 → **"Open pull request"** 를 클릭합니다.
3. PR 제목을 아래 형식으로 작성합니다:
   ```
   [Team N] 프로젝트 제출 - 팀이름
   ```
4. **Create pull request** 클릭하면 제출 완료!

> PR이 생성되면 코치가 확인 후 머지합니다. 머지 전까지 수정이 필요하면 같은 브랜치에 추가 커밋하시면 자동으로 PR에 반영됩니다.

---

## 피드백 확인 방법

코치의 피드백은 이 저장소의 **[Issues](../../issues)** 탭에서 확인할 수 있습니다.

자신의 팀 피드백을 빠르게 찾으려면 라벨(`Team 1`, `Team 2`, ...)로 필터링하세요.

---

## 주의사항

| | 규칙 |
|---|---|
| 1 | **자신의 팀 폴더에만 작업하세요.** 다른 팀의 폴더를 수정하면 안 됩니다. |
| 2 | **반드시 Pull Request를 통해 제출하세요.** 원본 저장소에 직접 push할 수 없습니다. |
| 3 | **팀 폴더 네이밍 규칙을 지켜주세요.** `team{번호}-{팀이름}` 형식이 아니면 피드백이 어려울 수 있습니다. |
| 4 | **PR 제출 전에 확인하세요.** 자신의 Fork에서 파일이 올바르게 들어갔는지 꼭 체크해주세요. |

---

## 도움이 필요하면?

- Git/GitHub 사용법이 어려우시면 코치에게 편하게 질문해주세요!
- 제출 과정에서 문제가 생기면 Issue를 열어주셔도 됩니다.
