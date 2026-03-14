package models

type Evento struct {
	Desc string
}

type User struct {
	User     string
	Password string
}

type Metadata struct {
	IP             string `json:"ip"`
	DeviceID       string `json:"device_id"`
	Geo            string `json:"geo"`
	SimulationUUID string `json:"simulation_uuid"`
}

var Users = map[string]User{
	"user1": {"user1", "user1"},
	"user2": {"user2", "user2"},
	"user3": {"user3", "user3"},
	"user4": {"user4", "user4"},
	"user5": {"user5", "user5"},
}

var userKeys = []string{"user1", "user2", "user3", "user4", "user5"}

func GetUserByIndex(index int) User {
	key := userKeys[index%len(userKeys)]
	return Users[key]
}
