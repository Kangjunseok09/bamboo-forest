import os
import pymysql
from flask import Flask, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]  # 세션(로그인 정보) 암호화 키, .env에서 읽음


# DB 연결 (비밀번호는 코드에 쓰지 않고 환경변수에서 읽음)
def get_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database="bamboo",
        cursorclass=pymysql.cursors.DictCursor,  # 결과를 row["컬럼명"]으로 꺼낼 수 있게
        autocommit=True,  # SQL 실행 즉시 반영
    )


# 메인: 글 목록 + 검색 + 좋아요 TOP 5
@app.route("/")
def index():
    q = request.args.get("q", "")  # 검색어 (없으면 빈 문자열)
    search_type = request.args.get("type", "all")  # 검색 기준: title / content / all
    keyword = "%" + q + "%"

    db = get_db()
    cur = db.cursor()
    # %s 자리에 값을 따로 넘겨서 SQL Injection 방지
    # 컬럼 이름은 사용자 입력을 그대로 넣지 않고, 정해진 SQL 중에서만 고름
    if search_type == "title":
        cur.execute("SELECT * FROM posts WHERE title LIKE %s ORDER BY id DESC", (keyword,))
    elif search_type == "content":
        cur.execute("SELECT * FROM posts WHERE content LIKE %s ORDER BY id DESC", (keyword,))
    else:
        search_type = "all"
        cur.execute("SELECT * FROM posts WHERE title LIKE %s OR content LIKE %s ORDER BY id DESC",
                    (keyword, keyword))
    posts = cur.fetchall()

    # 좋아요가 많은 글 5개 (JOIN + GROUP BY)
    cur.execute("""
        SELECT posts.id, posts.title, COUNT(*) AS like_count
        FROM likes JOIN posts ON likes.post_id = posts.id
        GROUP BY posts.id
        ORDER BY like_count DESC
        LIMIT 5
    """)
    hot = cur.fetchall()
    db.close()

    return render_template("index.html", posts=posts, hot=hot, q=q, search_type=search_type)


# 회원가입
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        # 아이디 중복 확인
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            db.close()
            flash("이미 있는 아이디예요.")
            return redirect("/register")

        # 비밀번호는 해시로 바꿔서 저장
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)",
                    (username, generate_password_hash(password)))
        db.commit()
        db.close()
        flash("가입 완료! 로그인해주세요.")
        return redirect("/login")

    return render_template("register.html")


# 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        db.close()

        # 아이디가 있고 비밀번호 해시가 맞으면 세션에 로그인 정보 저장
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect("/")

        flash("아이디 또는 비밀번호가 틀렸어요.")
        return redirect("/login")

    return render_template("login.html")


# 로그아웃: 세션 비우기
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# 글 상세: 글 + 댓글 + 좋아요 수
@app.route("/post/<int:post_id>")
def detail(post_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
    if post is None:  # 없는 글이면 목록으로
        db.close()
        return redirect("/")

    cur.execute("SELECT * FROM comments WHERE post_id = %s ORDER BY id", (post_id,))
    comments = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS cnt FROM likes WHERE post_id = %s", (post_id,))
    like_count = cur.fetchone()["cnt"]
    db.close()

    # 익명 닉네임: 글 작성자는 "글쓴이", 나머지는 댓글 단 순서대로 익명1, 익명2...
    nicknames = {post["user_id"]: "글쓴이"}
    for comment in comments:
        if comment["user_id"] not in nicknames:
            nicknames[comment["user_id"]] = "익명" + str(len(nicknames))
        comment["nickname"] = nicknames[comment["user_id"]]

    return render_template("post.html", post=post, comments=comments, like_count=like_count)


# 글쓰기 (로그인 필요)
@app.route("/write", methods=["GET", "POST"])
def write():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]

        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, %s, %s)",
                    (session["user_id"], title, content))
        db.commit()
        db.close()
        return redirect("/")

    return render_template("write.html", post=None)


# 글 수정 (본인 글만)
@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
def edit(post_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
    # 없는 글이거나 남의 글이면 막기
    if post is None or post["user_id"] != session["user_id"]:
        db.close()
        return redirect("/")

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        cur.execute("UPDATE posts SET title = %s, content = %s WHERE id = %s",
                    (title, content, post_id))
        db.commit()
        db.close()
        return redirect("/post/" + str(post_id))

    db.close()
    return render_template("write.html", post=post)  # 기존 내용이 채워진 글쓰기 화면


# 글 삭제 (본인 글만)
@app.route("/post/<int:post_id>/delete", methods=["POST"])
def delete(post_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
    if post is None or post["user_id"] != session["user_id"]:
        db.close()
        return redirect("/")

    # 트랜잭션: 댓글, 좋아요, 글을 한 번에 삭제. 중간에 실패하면 전부 되돌림
    try:
        db.begin()
        cur.execute("DELETE FROM comments WHERE post_id = %s", (post_id,))
        cur.execute("DELETE FROM likes WHERE post_id = %s", (post_id,))
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        db.commit()
    except Exception:
        db.rollback()
    db.close()

    return redirect("/")


# 댓글 작성 (로그인 필요)
@app.route("/post/<int:post_id>/comment", methods=["POST"])
def comment(post_id):
    if "user_id" not in session:
        return redirect("/login")

    content = request.form["content"]

    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s)",
                (post_id, session["user_id"], content))
    db.commit()
    db.close()

    return redirect("/post/" + str(post_id))


# 좋아요: 이미 눌렀으면 취소, 아니면 추가
@app.route("/post/<int:post_id>/like", methods=["POST"])
def like(post_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM likes WHERE user_id = %s AND post_id = %s",
                (session["user_id"], post_id))
    if cur.fetchone():
        cur.execute("DELETE FROM likes WHERE user_id = %s AND post_id = %s",
                    (session["user_id"], post_id))
    else:
        cur.execute("INSERT INTO likes (user_id, post_id) VALUES (%s, %s)",
                    (session["user_id"], post_id))
    db.commit()
    db.close()

    return redirect("/post/" + str(post_id))


# 서버 실행 (컨테이너 밖에서도 접속할 수 있게 0.0.0.0)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
