# SW Maestro Project

SW 마에스트로 프로젝트 제출 저장소입니다.

## Repository Structure

```
sw-maestro-project/
├── README.md
└── projects/
    ├── team1/
    ├── team2/
    ├── team3/
    ├── team4/
    └── team5/
```

각 팀은 `projects/` 아래 자신의 팀 폴더에 프로젝트를 제출합니다.

## How to Submit Your Project

### 1. Fork this repository

GitHub 페이지 우측 상단의 **Fork** 버튼을 클릭하여 자신의 GitHub 계정으로 Fork합니다.

### 2. Clone your fork

```bash
git clone https://github.com/<your-github-username>/sw-maestro-project.git
cd sw-maestro-project
```

### 3. Copy your project into your team folder

자신의 프로젝트를 해당 팀 폴더에 복사합니다.

```bash
cp -r /path/to/your-project/* projects/team1/
```

> `team1` 부분을 자신의 팀 번호로 변경하세요. (team1 ~ team5)

### 4. Commit and push

```bash
git add .
git commit -m "Team 1: Submit project"
git push origin main
```

### 5. Create a Pull Request

1. GitHub에서 자신의 Fork 저장소로 이동합니다.
2. **Contribute** → **Open pull request** 를 클릭합니다.
3. PR 제목을 `[Team N] 프로젝트 제출` 형식으로 작성합니다.
4. 제출 완료!

> PR이 머지되기 전까지 리뷰가 진행될 수 있습니다.

## Important

- **자신의 팀 폴더에만 작업하세요.** 다른 팀의 폴더를 수정하지 마세요.
- **반드시 Pull Request를 통해 제출하세요.** 직접 push는 허용되지 않습니다.
- PR 제출 전 자신의 Fork에서 프로젝트가 정상적으로 포함되었는지 확인하세요.
