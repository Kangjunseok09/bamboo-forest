import os
import pymysql
from flask import Flask, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]


def get_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database="bamboo",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@app.route("/")
def index():
    q = request.args.get("q", "")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE title LIKE %s ORDER BY id DESC", ("%" + q + "%",))
    posts = cur.fetchall()

    cur.execute("""
        SELECT posts.id, posts.title, COUNT(*) AS like_count
        FROM likes JOIN posts ON likes.post_id = posts.id
        GROUP BY posts.id
        ORDER BY like_count DESC
        LIMIT 5
    """)
    hot = cur.fetchall()
    db.close()

    return render_template("index.html", posts=posts, hot=hot, q=q)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            db.close()
            flash("이미 있는 아이디예요.")
            return redirect("/register")

        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)",
                    (username, generate_password_hash(password)))
        db.commit()
        db.close()
        flash("가입 완료! 로그인해주세요.")
        return redirect("/login")

    return render_template("register.html")


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

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect("/")

        flash("아이디 또는 비밀번호가 틀렸어요.")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/post/<int:post_id>")
def detail(post_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
    if post is None:
        db.close()
        return redirect("/")

    cur.execute("SELECT * FROM comments WHERE post_id = %s ORDER BY id", (post_id,))
    comments = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS cnt FROM likes WHERE post_id = %s", (post_id,))
    like_count = cur.fetchone()["cnt"]
    db.close()

    nicknames = {post["user_id"]: "글쓴이"}
    for comment in comments:
        if comment["user_id"] not in nicknames:
            nicknames[comment["user_id"]] = "익명" + str(len(nicknames))
        comment["nickname"] = nicknames[comment["user_id"]]

    return render_template("post.html", post=post, comments=comments, like_count=like_count)


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


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
def edit(post_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
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
    return render_template("write.html", post=post)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
