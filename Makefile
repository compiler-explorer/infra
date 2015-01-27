.NOTPARALLEL: 
all: docker-image

docker-image:
	sudo docker build .

clean:
	echo nothing to clean yet

.PHONY: all clean docker-image 
